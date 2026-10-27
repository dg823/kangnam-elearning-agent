package com.songkeeper.app.data

import java.io.BufferedInputStream
import java.io.InputStream
import java.security.MessageDigest

/**
 * 파일 이름·제목·가수 같은 태그가 달라도 소리 데이터가 같으면 같은 값이 나오도록,
 * 앞의 ID3v2 태그와 뒤의 ID3v1 태그(128바이트)를 뺀 나머지를 SHA-256으로 해시한다.
 * (태그 편집만으로 달라진 MP3 사본을 같은 곡으로 알아보기 위함)
 */
object AudioHasher {
    private const val CHUNK = 64 * 1024
    private const val ID3V1_SIZE = 128

    fun hash(input: InputStream): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val stream = BufferedInputStream(input, CHUNK)

        // ID3v2 헤더: "ID3" + 버전 2바이트 + 플래그 1바이트 + synchsafe 크기 4바이트
        val header = ByteArray(10)
        val headerLen = readFully(stream, header)
        val hasId3v2 = headerLen == 10 &&
            header[0] == 'I'.code.toByte() && header[1] == 'D'.code.toByte() && header[2] == '3'.code.toByte() &&
            (6..9).all { header[it] in 0..0x7F }
        if (hasId3v2) {
            var size = 0L
            for (i in 6..9) size = (size shl 7) or header[i].toLong()
            if (header[5].toInt() and 0x10 != 0) size += 10 // 푸터가 있으면 10바이트 더
            skipFully(stream, size)
        } else {
            digest.update(header, 0, headerLen)
        }

        // 마지막 128바이트는 ID3v1 태그일 수 있으므로 끝까지 읽은 뒤에 판단한다.
        val work = ByteArray(ID3V1_SIZE + CHUNK)
        var held = 0
        while (true) {
            val n = stream.read(work, held, CHUNK)
            if (n < 0) break
            val total = held + n
            if (total > ID3V1_SIZE) {
                digest.update(work, 0, total - ID3V1_SIZE)
                System.arraycopy(work, total - ID3V1_SIZE, work, 0, ID3V1_SIZE)
                held = ID3V1_SIZE
            } else {
                held = total
            }
        }
        val hasId3v1 = held == ID3V1_SIZE &&
            work[0] == 'T'.code.toByte() && work[1] == 'A'.code.toByte() && work[2] == 'G'.code.toByte()
        if (!hasId3v1) digest.update(work, 0, held)

        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private fun readFully(stream: InputStream, buf: ByteArray): Int {
        var off = 0
        while (off < buf.size) {
            val n = stream.read(buf, off, buf.size - off)
            if (n < 0) break
            off += n
        }
        return off
    }

    private fun skipFully(stream: InputStream, count: Long) {
        var left = count
        while (left > 0) {
            val skipped = stream.skip(left)
            if (skipped > 0) {
                left -= skipped
            } else if (stream.read() < 0) {
                return
            } else {
                left--
            }
        }
    }
}
