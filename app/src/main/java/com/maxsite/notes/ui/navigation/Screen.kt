package com.maxsite.notes.ui.navigation

sealed class Screen(val route: String) {
    data object Splash : Screen("splash")
    data object NotesList : Screen("notes_list")
    data object AddNote : Screen("add_note")
    data object ViewNote : Screen("view_note/{noteId}") {
        fun createRoute(noteId: Long) = "view_note/$noteId"
    }
}
