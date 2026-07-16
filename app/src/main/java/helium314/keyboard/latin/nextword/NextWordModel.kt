// SPDX-License-Identifier: Apache-2.0 AND GPL-3.0-only
package helium314.keyboard.latin.nextword

import android.content.res.AssetFileDescriptor
import helium314.keyboard.latin.NgramContext
import java.io.File
import java.io.FileInputStream
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.channels.FileChannel
import java.util.Locale

internal data class NextWordCandidate(val word: String, val score: Int)

internal class NextWordModel private constructor(private val buffer: ByteBuffer) {
    val language: String
    val fileSize: Int = buffer.capacity()

    private val wordCount: Int
    private val tableSize: Int
    private val candidateCount: Int
    private val offsetsOffset: Int
    private val poolOffset: Int
    private val tableOffset: Int
    private val candidatesOffset: Int

    init {
        buffer.order(ByteOrder.LITTLE_ENDIAN)
        requireAvailable(0, FIXED_HEADER_SIZE)
        if (buffer.get(0) != 'N'.code.toByte()
            || buffer.get(1) != 'W'.code.toByte()
            || buffer.get(2) != 'L'.code.toByte()
            || buffer.get(3) != 'M'.code.toByte()
        ) {
            throw NextWordModelFormatException("invalid NWLM magic")
        }
        val version = unsignedByte(4)
        if (version != VERSION) {
            throw NextWordModelFormatException("unsupported NWLM version $version")
        }
        val languageLength = unsignedByte(5)
        wordCount = nonNegativeInt(6, "word count")
        tableSize = nonNegativeInt(10, "table size")
        candidateCount = nonNegativeInt(14, "candidate count")
        if (wordCount > MAX_U24) {
            throw NextWordModelFormatException("word count exceeds u24")
        }
        if (tableSize == 0 || tableSize and (tableSize - 1) != 0) {
            throw NextWordModelFormatException("table size is not a power of two")
        }

        val languageOffset = FIXED_HEADER_SIZE
        requireAvailable(languageOffset, languageLength)
        language = readUtf8(languageOffset, languageLength)
        if (language.isEmpty()) {
            throw NextWordModelFormatException("empty language tag")
        }

        offsetsOffset = checkedAdd(languageOffset, languageLength, "word offsets")
        val offsetsSize = checkedMultiply(wordCount + 1L, INT_SIZE.toLong(), "word offsets")
        requireAvailable(offsetsOffset, offsetsSize)
        poolOffset = checkedAdd(offsetsOffset, offsetsSize, "word pool")
        val poolSize = nonNegativeInt(offsetsOffset + wordCount * INT_SIZE, "word pool size")
        requireAvailable(poolOffset, poolSize)
        tableOffset = checkedAdd(poolOffset, poolSize, "hash table")
        val tableBytes = checkedMultiply(tableSize.toLong(), TABLE_ENTRY_SIZE.toLong(), "hash table")
        requireAvailable(tableOffset, tableBytes)
        candidatesOffset = checkedAdd(tableOffset, tableBytes, "candidates")
        val candidateBytes = checkedMultiply(candidateCount.toLong(), CANDIDATE_SIZE.toLong(), "candidates")
        val expectedSize = checkedAdd(candidatesOffset, candidateBytes, "model end")
        if (expectedSize != buffer.capacity()) {
            throw NextWordModelFormatException(
                "model size mismatch: expected $expectedSize, got ${buffer.capacity()}"
            )
        }
    }

    fun predict(ngramContext: NgramContext, locale: Locale): List<NextWordCandidate> {
        if (ngramContext.isBeginningOfSentenceContext) {
            return lookup(BOS_CONTEXT).take(MAX_RESULTS)
        }
        val recent = ngramContext.getNthPrevWord(1)?.toString().orEmpty()
        if (recent.isEmpty() || isUnsafeContextWord(recent)) {
            return emptyList()
        }
        val older = if (ngramContext.isNthPrevWordBeginningOfSentence(2)) {
            ""
        } else {
            ngramContext.getNthPrevWord(2)?.toString().orEmpty()
        }
        if (older.isNotEmpty() && isUnsafeContextWord(older)) {
            return emptyList()
        }

        val recentKey = normalizeKey(recent, locale)
        val olderKey = if (older.isEmpty()) "" else normalizeKey(older, locale)
        val result = ArrayList<NextWordCandidate>(MAX_RESULTS)
        val seen = HashSet<String>(MAX_RESULTS * 2)
        if (olderKey.isNotEmpty()) {
            appendCandidates(lookup("$olderKey$CONTEXT_SEPARATOR$recentKey"), 0, locale, seen, result)
        }
        if (result.size < MAX_RESULTS) {
            appendCandidates(lookup(recentKey), BACKOFF_PENALTY, locale, seen, result)
        }
        return result
    }

    internal fun lookup(context: String): List<NextWordCandidate> {
        val keyHash = XxHash64.hash(context.toByteArray(Charsets.UTF_8))
        if (keyHash == 0L) return emptyList()
        var slot = (keyHash and (tableSize - 1).toLong()).toInt()
        repeat(tableSize) {
            val entryOffset = tableOffset + slot * TABLE_ENTRY_SIZE
            val storedHash = buffer.getLong(entryOffset)
            if (storedHash == 0L) return emptyList()
            if (storedHash == keyHash) {
                val candidateStart = nonNegativeInt(entryOffset + LONG_SIZE, "candidate start")
                val count = unsignedByte(entryOffset + LONG_SIZE + INT_SIZE)
                if (count > MAX_MODEL_CANDIDATES || candidateStart.toLong() + count > candidateCount) {
                    throw NextWordModelFormatException("invalid candidate range")
                }
                val result = ArrayList<NextWordCandidate>(count)
                repeat(count) { index ->
                    val candidateOffset = candidatesOffset + (candidateStart + index) * CANDIDATE_SIZE
                    val wordId = unsignedByte(candidateOffset) or
                        (unsignedByte(candidateOffset + 1) shl 8) or
                        (unsignedByte(candidateOffset + 2) shl 16)
                    val score = unsignedByte(candidateOffset + 3)
                    if (wordId >= wordCount || score == 0) {
                        throw NextWordModelFormatException("invalid candidate")
                    }
                    result.add(NextWordCandidate(readWord(wordId), score))
                }
                return result
            }
            slot = (slot + 1) and (tableSize - 1)
        }
        throw NextWordModelFormatException("hash table contains no empty slot")
    }

    private fun appendCandidates(
        candidates: List<NextWordCandidate>,
        penalty: Int,
        locale: Locale,
        seen: MutableSet<String>,
        result: MutableList<NextWordCandidate>
    ) {
        for (candidate in candidates) {
            if (!seen.add(normalizeKey(candidate.word, locale))) continue
            result.add(candidate.copy(score = (candidate.score - penalty).coerceAtLeast(1)))
            if (result.size == MAX_RESULTS) return
        }
    }

    private fun readWord(wordId: Int): String {
        val start = nonNegativeInt(offsetsOffset + wordId * INT_SIZE, "word offset")
        val end = nonNegativeInt(offsetsOffset + (wordId + 1) * INT_SIZE, "word offset")
        if (start > end || poolOffset.toLong() + end > tableOffset) {
            throw NextWordModelFormatException("invalid word offsets")
        }
        return readUtf8(poolOffset + start, end - start)
    }

    private fun readUtf8(offset: Int, length: Int): String {
        requireAvailable(offset, length)
        val bytes = ByteArray(length)
        for (index in bytes.indices) bytes[index] = buffer.get(offset + index)
        return bytes.toString(Charsets.UTF_8)
    }

    private fun unsignedByte(offset: Int): Int = buffer.get(offset).toInt() and 0xFF

    private fun nonNegativeInt(offset: Int, section: String): Int {
        requireAvailable(offset, INT_SIZE)
        return buffer.getInt(offset).also {
            if (it < 0) throw NextWordModelFormatException("negative $section")
        }
    }

    private fun requireAvailable(offset: Int, length: Int) {
        if (offset < 0 || length < 0 || offset.toLong() + length > buffer.capacity()) {
            throw NextWordModelFormatException("truncated model")
        }
    }

    private fun checkedAdd(offset: Int, length: Int, section: String): Int =
        checkedAdd(offset, length.toLong(), section)

    private fun checkedAdd(offset: Int, length: Long, section: String): Int {
        val result = offset.toLong() + length
        if (result !in 0..Int.MAX_VALUE.toLong()) {
            throw NextWordModelFormatException("$section offset overflow")
        }
        return result.toInt()
    }

    private fun checkedMultiply(left: Long, right: Long, section: String): Int {
        if (left < 0 || right < 0 || left != 0L && right > Int.MAX_VALUE / left) {
            throw NextWordModelFormatException("$section size overflow")
        }
        return (left * right).toInt()
    }

    companion object {
        private const val VERSION = 1
        private const val FIXED_HEADER_SIZE = 18
        private const val LONG_SIZE = 8
        private const val INT_SIZE = 4
        private const val TABLE_ENTRY_SIZE = 13
        private const val CANDIDATE_SIZE = 4
        private const val MAX_MODEL_CANDIDATES = 4
        private const val MAX_RESULTS = 3
        private const val MAX_U24 = 0xFFFFFF
        private const val BACKOFF_PENALTY = 11
        private const val BOS_CONTEXT = "\u0002"
        private const val CONTEXT_SEPARATOR = "\u0001"

        fun fromAsset(asset: AssetFileDescriptor): NextWordModel {
            if (asset.length <= 0 || asset.length > Int.MAX_VALUE) {
                throw NextWordModelFormatException("invalid asset length ${asset.length}")
            }
            // The caller owns the AssetFileDescriptor. Closing it after map() releases the shared
            // file descriptor while the mapped pages remain valid.
            val mapped = FileInputStream(asset.fileDescriptor).channel.map(
                FileChannel.MapMode.READ_ONLY,
                asset.startOffset,
                asset.length
            )
            return NextWordModel(mapped)
        }

        internal fun fromFile(file: File): NextWordModel {
            val size = file.length()
            if (size <= 0 || size > Int.MAX_VALUE) {
                throw NextWordModelFormatException("invalid file length $size")
            }
            val mapped = FileInputStream(file).channel.use { channel ->
                channel.map(FileChannel.MapMode.READ_ONLY, 0, size)
            }
            return NextWordModel(mapped)
        }

        internal fun normalizeKey(word: String, locale: Locale): String {
            var normalized = word.replace('\u2019', '\'').lowercase(locale)
            if (locale.language == "ru") normalized = normalized.replace('ё', 'е')
            return normalized
        }

        private fun isUnsafeContextWord(word: String): Boolean {
            if (word.any(Char::isDigit)) return true
            return word.any { it == '@' || it == '/' || it == '\\' || it == ':' || it == '.' }
                || word.startsWith("www", ignoreCase = true)
        }
    }
}

internal class NextWordModelFormatException(message: String) : IOException(message)

private object XxHash64 {
    private const val PRIME_1: ULong = 11400714785074694791uL
    private const val PRIME_2: ULong = 14029467366897019727uL
    private const val PRIME_3: ULong = 1609587929392839161uL
    private const val PRIME_4: ULong = 9650029242287828579uL
    private const val PRIME_5: ULong = 2870177450012600261uL

    fun hash(data: ByteArray, seed: ULong = 0uL): Long {
        var offset = 0
        val digestStart: ULong
        if (data.size >= 32) {
            var v1 = seed + PRIME_1 + PRIME_2
            var v2 = seed + PRIME_2
            var v3 = seed
            var v4 = seed - PRIME_1
            val limit = data.size - 32
            while (offset <= limit) {
                v1 = round(v1, readLong(data, offset)); offset += 8
                v2 = round(v2, readLong(data, offset)); offset += 8
                v3 = round(v3, readLong(data, offset)); offset += 8
                v4 = round(v4, readLong(data, offset)); offset += 8
            }
            var digest = rotateLeft(v1, 1) + rotateLeft(v2, 7) + rotateLeft(v3, 12) + rotateLeft(v4, 18)
            digest = mergeRound(digest, v1)
            digest = mergeRound(digest, v2)
            digest = mergeRound(digest, v3)
            digestStart = mergeRound(digest, v4)
        } else {
            digestStart = seed + PRIME_5
        }

        var digest = digestStart + data.size.toULong()
        while (offset + 8 <= data.size) {
            digest = digest xor round(0uL, readLong(data, offset))
            digest = rotateLeft(digest, 27) * PRIME_1 + PRIME_4
            offset += 8
        }
        if (offset + 4 <= data.size) {
            digest = digest xor (readInt(data, offset) * PRIME_1)
            digest = rotateLeft(digest, 23) * PRIME_2 + PRIME_3
            offset += 4
        }
        while (offset < data.size) {
            digest = digest xor (data[offset].toUByte().toULong() * PRIME_5)
            digest = rotateLeft(digest, 11) * PRIME_1
            offset += 1
        }
        digest = digest xor (digest shr 33)
        digest *= PRIME_2
        digest = digest xor (digest shr 29)
        digest *= PRIME_3
        digest = digest xor (digest shr 32)
        return digest.toLong()
    }

    private fun round(accumulator: ULong, lane: ULong): ULong =
        rotateLeft(accumulator + lane * PRIME_2, 31) * PRIME_1

    private fun mergeRound(accumulator: ULong, value: ULong): ULong =
        (accumulator xor round(0uL, value)) * PRIME_1 + PRIME_4

    private fun rotateLeft(value: ULong, count: Int): ULong =
        (value shl count) or (value shr (64 - count))

    private fun readLong(data: ByteArray, offset: Int): ULong {
        var result = 0uL
        repeat(8) { index ->
            result = result or (data[offset + index].toUByte().toULong() shl (index * 8))
        }
        return result
    }

    private fun readInt(data: ByteArray, offset: Int): ULong {
        var result = 0uL
        repeat(4) { index ->
            result = result or (data[offset + index].toUByte().toULong() shl (index * 8))
        }
        return result
    }
}
