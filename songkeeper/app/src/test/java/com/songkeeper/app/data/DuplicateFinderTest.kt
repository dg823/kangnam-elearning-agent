package com.songkeeper.app.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DuplicateFinderTest {
    private fun song(
        id: Long,
        title: String = "t$id",
        artist: String = "가수",
        durationMs: Long = 200_000,
        size: Long = 8_000_000,
        hash: String? = null,
        addedAt: Long = id,
    ) = Song(id, "content://$id", title, artist, "앨범", durationMs, size, addedAt, hash)

    @Test
    fun `제목이 달라도 해시가 같으면 완전 중복`() {
        val songs = listOf(
            song(1, title = "Hello", hash = "aaa"),
            song(2, title = "헬로 (복사본)", hash = "aaa"),
            song(3, title = "Other", hash = "bbb", durationMs = 100_000),
        )
        val r = DuplicateFinder.find(songs)
        assertEquals(1, r.exact.size)
        assertEquals(listOf(1L, 2L), r.exact[0].songs.map { it.id })
        assertTrue(r.exact[0].exact)
        assertTrue(r.similar.isEmpty())
    }

    @Test
    fun `해시가 없는 곡은 완전 중복으로 묶지 않는다`() {
        val r = DuplicateFinder.find(listOf(song(1), song(2, durationMs = 90_000)))
        assertTrue(r.exact.isEmpty())
    }

    @Test
    fun `길이 크기 가수가 비슷하면 후보`() {
        val songs = listOf(
            song(1, hash = "a", durationMs = 200_000, size = 8_000_000),
            song(2, hash = "b", durationMs = 200_300, size = 8_100_000, title = "다른 제목"),
        )
        val r = DuplicateFinder.find(songs)
        assertTrue(r.exact.isEmpty())
        assertEquals(1, r.similar.size)
        assertEquals(setOf(1L, 2L), r.similar[0].songs.map { it.id }.toSet())
    }

    @Test
    fun `가수가 다르거나 길이 차이가 크면 후보 아님`() {
        val songs = listOf(
            song(1, hash = "a"),
            song(2, hash = "b", artist = "다른 가수"),
            song(3, hash = "c", durationMs = 210_000),
            song(4, hash = "d", size = 4_000_000),
        )
        assertTrue(DuplicateFinder.find(songs).similar.isEmpty())
    }

    @Test
    fun `완전 중복 묶음은 후보 비교에서 한 곡으로 센다`() {
        val songs = listOf(
            song(1, hash = "a"),
            song(2, hash = "a"),
            song(3, hash = "b", durationMs = 200_100),
        )
        val r = DuplicateFinder.find(songs)
        assertEquals(1, r.exact.size)
        assertEquals(1, r.similar.size)
        assertEquals(listOf(1L, 3L), r.similar[0].songs.map { it.id }.sorted())
    }

    @Test
    fun `길이 정보가 없는 곡은 후보에서 제외`() {
        val songs = listOf(song(1, durationMs = 0), song(2, durationMs = 0))
        assertTrue(DuplicateFinder.find(songs).similar.isEmpty())
    }
}
