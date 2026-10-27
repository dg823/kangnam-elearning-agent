package com.songkeeper.app.data

import kotlin.math.abs
import kotlin.math.max

/** [exact]: 오디오 데이터가 완전히 같음. 그렇지 않으면 길이·크기·가수가 비슷한 "후보"로 직접 들어보고 판단. */
data class DuplicateGroup(val key: String, val songs: List<Song>, val exact: Boolean)

data class DuplicateResult(
    val exact: List<DuplicateGroup> = emptyList(),
    val similar: List<DuplicateGroup> = emptyList(),
)

object DuplicateFinder {
    const val DURATION_TOLERANCE_MS = 500L
    const val SIZE_TOLERANCE = 0.03

    fun find(songs: List<Song>): DuplicateResult {
        val exact = songs
            .filter { it.contentHash != null }
            .groupBy { it.contentHash!! }
            .filterValues { it.size > 1 }
            .map { (hash, list) -> DuplicateGroup(hash, list.sortedBy { it.addedAt }, exact = true) }

        // 완전 동일 그룹은 대표 한 곡만 남겨서 후보 비교에 넣는다.
        val representatives = songs
            .groupBy { it.contentHash ?: "id:${it.id}" }
            .values
            .map { it.minBy { s -> s.addedAt } }
            .filter { it.durationMs > 0 }
            .sortedBy { it.durationMs }

        val similar = ArrayList<DuplicateGroup>()
        var current = ArrayList<Song>()
        fun flush() {
            if (current.size > 1) {
                val key = "s:" + current.map { it.id }.sorted().joinToString(",")
                similar += DuplicateGroup(key, current.toList(), exact = false)
            }
            current = ArrayList()
        }
        for (song in representatives) {
            if (current.isNotEmpty() && isSimilar(current.first(), song)) {
                current += song
            } else {
                flush()
                current += song
            }
        }
        flush()

        return DuplicateResult(exact, similar)
    }

    private fun isSimilar(a: Song, b: Song): Boolean =
        abs(a.durationMs - b.durationMs) <= DURATION_TOLERANCE_MS &&
            abs(a.sizeBytes - b.sizeBytes) <= SIZE_TOLERANCE * max(a.sizeBytes, b.sizeBytes) &&
            a.artist.equals(b.artist, ignoreCase = true)
}
