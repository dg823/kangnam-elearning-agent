package com.songkeeper.app.data

import android.content.ContentUris
import android.content.Context
import android.provider.MediaStore

object MediaScanner {
    private const val UNKNOWN = "알 수 없음"

    fun query(context: Context): List<Song> {
        val collection = MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
        val projection = arrayOf(
            MediaStore.Audio.Media._ID,
            MediaStore.Audio.Media.TITLE,
            MediaStore.Audio.Media.ARTIST,
            MediaStore.Audio.Media.ALBUM,
            MediaStore.Audio.Media.DURATION,
            MediaStore.Audio.Media.SIZE,
            MediaStore.Audio.Media.DATE_ADDED,
        )
        val songs = ArrayList<Song>()
        context.contentResolver.query(
            collection,
            projection,
            "${MediaStore.Audio.Media.IS_MUSIC} != 0",
            null,
            null,
        )?.use { c ->
            val idCol = c.getColumnIndexOrThrow(MediaStore.Audio.Media._ID)
            val titleCol = c.getColumnIndexOrThrow(MediaStore.Audio.Media.TITLE)
            val artistCol = c.getColumnIndexOrThrow(MediaStore.Audio.Media.ARTIST)
            val albumCol = c.getColumnIndexOrThrow(MediaStore.Audio.Media.ALBUM)
            val durationCol = c.getColumnIndexOrThrow(MediaStore.Audio.Media.DURATION)
            val sizeCol = c.getColumnIndexOrThrow(MediaStore.Audio.Media.SIZE)
            val addedCol = c.getColumnIndexOrThrow(MediaStore.Audio.Media.DATE_ADDED)
            while (c.moveToNext()) {
                val id = c.getLong(idCol)
                songs += Song(
                    id = id,
                    uri = ContentUris.withAppendedId(collection, id).toString(),
                    title = c.getString(titleCol).cleanOr("제목 없음"),
                    artist = c.getString(artistCol).cleanOr(UNKNOWN),
                    album = c.getString(albumCol).cleanOr(UNKNOWN),
                    durationMs = c.getLong(durationCol),
                    sizeBytes = c.getLong(sizeCol),
                    addedAt = c.getLong(addedCol),
                )
            }
        }
        return songs
    }

    private fun String?.cleanOr(fallback: String): String =
        if (this.isNullOrBlank() || this == "<unknown>") fallback else this
}
