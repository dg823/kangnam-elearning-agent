package com.songkeeper.app.data

import androidx.room.Entity
import androidx.room.PrimaryKey

/** MediaStore에서 읽어 온 곡 한 개. [contentHash]는 태그를 뺀 오디오 데이터의 SHA-256. */
@Entity(tableName = "songs")
data class Song(
    @PrimaryKey val id: Long,
    val uri: String,
    val title: String,
    val artist: String,
    val album: String,
    val durationMs: Long,
    val sizeBytes: Long,
    val addedAt: Long,
    val contentHash: String? = null,
    val hidden: Boolean = false,
)
