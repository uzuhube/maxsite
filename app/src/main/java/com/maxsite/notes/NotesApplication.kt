package com.maxsite.notes

import android.app.Application
import com.maxsite.notes.data.NotesDatabase
import com.maxsite.notes.data.NotesRepository

class NotesApplication : Application() {

    val database by lazy { NotesDatabase.getDatabase(this) }
    val repository by lazy { NotesRepository(database.noteDao()) }
}
