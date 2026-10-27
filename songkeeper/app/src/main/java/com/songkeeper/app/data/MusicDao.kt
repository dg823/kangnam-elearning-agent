package com.songkeeper.app.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
abstract class MusicDao {

    // ---- 곡 ----

    @Query("SELECT * FROM songs")
    abstract suspend fun allSongs(): List<Song>

    @Query("SELECT * FROM songs WHERE hidden = 0")
    abstract fun visibleSongs(): Flow<List<Song>>

    @Query("SELECT COUNT(*) FROM songs WHERE hidden = 1")
    abstract fun hiddenCount(): Flow<Int>

    @Query("SELECT * FROM songs WHERE contentHash IS NULL")
    abstract suspend fun unhashed(): List<Song>

    // REPLACE를 쓰면 외래키 CASCADE로 태그·재생목록이 지워지므로 IGNORE + 별도 UPDATE를 쓴다.
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    abstract suspend fun insertSongs(songs: List<Song>)

    @Update
    abstract suspend fun updateSongs(songs: List<Song>)

    @Query("DELETE FROM songs WHERE id IN (:ids)")
    abstract suspend fun deleteSongs(ids: List<Long>)

    @Query("UPDATE songs SET contentHash = :hash WHERE id = :id")
    abstract suspend fun setHash(id: Long, hash: String)

    @Query("UPDATE songs SET hidden = :hidden WHERE id IN (:ids)")
    abstract suspend fun setHidden(ids: List<Long>, hidden: Boolean)

    @Query("UPDATE songs SET hidden = 0 WHERE hidden = 1")
    abstract suspend fun restoreHidden()

    // ---- 태그 ----

    @Query("SELECT * FROM song_tags")
    abstract fun allSongTags(): Flow<List<SongTag>>

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    abstract suspend fun insertTags(tags: List<SongTag>)

    @Query("DELETE FROM song_tags WHERE songId = :songId")
    abstract suspend fun clearTags(songId: Long)

    @Transaction
    open suspend fun setTags(songId: Long, tags: Set<String>) {
        clearTags(songId)
        insertTags(tags.map { SongTag(songId, it) })
    }

    // ---- 플레이리스트 ----

    @Query("SELECT * FROM playlists ORDER BY name")
    abstract fun playlists(): Flow<List<Playlist>>

    @Query("SELECT * FROM playlist_songs ORDER BY playlistId, position")
    abstract fun playlistEntries(): Flow<List<PlaylistSong>>

    @Insert
    abstract suspend fun insertPlaylist(playlist: Playlist): Long

    @Query("DELETE FROM playlists WHERE id = :id")
    abstract suspend fun deletePlaylist(id: Long)

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    abstract suspend fun insertEntry(entry: PlaylistSong)

    @Query("SELECT COALESCE(MAX(position), -1) + 1 FROM playlist_songs WHERE playlistId = :playlistId")
    abstract suspend fun nextPosition(playlistId: Long): Int

    @Transaction
    open suspend fun addToPlaylist(playlistId: Long, songId: Long) {
        insertEntry(PlaylistSong(playlistId, songId, nextPosition(playlistId)))
    }

    @Query("DELETE FROM playlist_songs WHERE playlistId = :playlistId AND songId = :songId")
    abstract suspend fun removeFromPlaylist(playlistId: Long, songId: Long)

    // ---- 중복 합치기 ----

    @Query("UPDATE OR IGNORE playlist_songs SET songId = :keep WHERE songId = :dup")
    abstract suspend fun repointEntries(keep: Long, dup: Long)

    @Query("INSERT OR IGNORE INTO song_tags (songId, tag) SELECT :keep, tag FROM song_tags WHERE songId = :dup")
    abstract suspend fun copyTags(keep: Long, dup: Long)

    /** [dups]의 재생목록 항목과 태그를 [keep]으로 옮기고 [dups]는 라이브러리에서 숨긴다. */
    @Transaction
    open suspend fun mergeInto(keep: Long, dups: List<Long>) {
        dups.forEach {
            repointEntries(keep, it)
            copyTags(keep, it)
        }
        setHidden(dups, true)
    }
}
