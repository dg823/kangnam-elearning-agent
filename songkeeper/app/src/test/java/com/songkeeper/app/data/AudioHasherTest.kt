package com.songkeeper.app.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test
import java.io.ByteArrayInputStream
import java.util.Random

class AudioHasherTest {
    private val audio = ByteArray(300_000).also { Random(1).nextBytes(it) }

    private fun id3v2(payload: ByteArray, footer: Boolean = false): ByteArray {
        val size = payload.size
        val header = byteArrayOf(
            'I'.code.toByte(), 'D'.code.toByte(), '3'.code.toByte(), 3, 0,
            if (footer) 0x10 else 0,
            ((size shr 21) and 0x7F).toByte(), ((size shr 14) and 0x7F).toByte(),
            ((size shr 7) and 0x7F).toByte(), (size and 0x7F).toByte(),
        )
        return header + payload + (if (footer) ByteArray(10) else ByteArray(0))
    }

    private fun id3v1(title: String): ByteArray {
        val tag = ByteArray(128)
        "TAG".toByteArray().copyInto(tag)
        title.toByteArray().copyInto(tag, 3)
        return tag
    }

    private fun hash(bytes: ByteArray) = AudioHasher.hash(ByteArrayInputStream(bytes))

    @Test
    fun `같은 소리에 태그만 다르면 같은 해시`() {
        val a = id3v2(ByteArray(500) { 1 }) + audio + id3v1("노래 A")
        val b = id3v2(ByteArray(12_345) { 2 }) + audio
        val c = audio + id3v1("완전히 다른 제목")
        val bare = audio
        assertEquals(hash(bare), hash(a))
        assertEquals(hash(bare), hash(b))
        assertEquals(hash(bare), hash(c))
    }

    @Test
    fun `푸터가 있는 ID3v2도 건너뛴다`() {
        assertEquals(hash(audio), hash(id3v2(ByteArray(100), footer = true) + audio))
    }

    @Test
    fun `소리가 다르면 다른 해시`() {
        val other = audio.copyOf().also { it[150_000] = (it[150_000] + 1).toByte() }
        assertNotEquals(hash(audio), hash(other))
    }

    @Test
    fun `아주 작은 파일과 빈 파일도 처리한다`() {
        hash(ByteArray(0))
        hash(ByteArray(5))
        assertEquals(hash(ByteArray(50)), hash(ByteArray(50)))
        assertNotEquals(hash(ByteArray(50)), hash(ByteArray(51)))
    }

    @Test
    fun `TAG로 시작하는 마지막 128바이트가 아니면 해시에 포함`() {
        val tail = ByteArray(128) { 7 }
        assertNotEquals(hash(audio), hash(audio + tail))
    }
}
