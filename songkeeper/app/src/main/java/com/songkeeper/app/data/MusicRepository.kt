package com.songkeeper.app.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import android.net.Uri

class MusicRepository(private val context: Context, private val dao: MusicDao) {

    /** MediaStore와 DB를 맞춘다. 기존 곡의 해시·숨김 상태는 파일 크기가 같으면 유지한다. */
    suspend fun scan(): Int = withContext(Dispatchers.IO) {
        val scanned = MediaScanner.query(context)
        val existing = dao.allSongs().associateBy { it.id }

        val toInsert = ArrayList<Song>()
        val toUpdate = ArrayList<Song>()
        for (song in scanned) {
            val old = existing[song.id]
            if (old == null) {
                toInsert += song
            } else {
                val merged = song.copy(
                    contentHash = if (old.sizeBytes == song.sizeBytes) old.contentHash else null,
                    hidden = old.hidden,
                )
                if (merged != old) toUpdate += merged
            }
        }
        val gone = existing.keys - scanned.map { it.id }.toSet()

        dao.insertSongs(toInsert)
        dao.updateSongs(toUpdate)
        gone.toList().chunked(500).forEach { dao.deleteSongs(it) }
        scanned.size
    }

    /** 아직 해시가 없는 곡들의 내용 해시를 계산한다. 읽기에 실패한 곡은 건너뛴다. */
    suspend fun hashPending(onProgress: (done: Int, total: Int) -> Unit) = withContext(Dispatchers.IO) {
        val pending = dao.unhashed()
        onProgress(0, pending.size)
        pending.forEachIndexed { index, song ->
            val hash = runCatching {
                context.contentResolver.openInputStream(Uri.parse(song.uri))?.use { AudioHasher.hash(it) }
            }.getOrNull()
            if (hash != null) dao.setHash(song.id, hash)
            onProgress(index + 1, pending.size)
        }
    }
}
