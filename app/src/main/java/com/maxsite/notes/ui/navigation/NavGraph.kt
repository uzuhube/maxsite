package com.maxsite.notes.ui.navigation

import androidx.compose.runtime.Composable
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.maxsite.notes.ui.screens.AddNoteScreen
import com.maxsite.notes.ui.screens.NotesListScreen
import com.maxsite.notes.ui.screens.SplashScreen
import com.maxsite.notes.ui.screens.ViewNoteScreen
import com.maxsite.notes.ui.screens.NotesViewModel
import com.maxsite.notes.ui.screens.NotesViewModelFactory

@Composable
fun NavGraph(
    navController: NavHostController,
    viewModelFactory: NotesViewModelFactory
) {
    val viewModel: NotesViewModel = viewModel(factory = viewModelFactory)

    NavHost(
        navController = navController,
        startDestination = Screen.Splash.route
    ) {
        composable(Screen.Splash.route) {
            SplashScreen(
                onSplashFinished = {
                    navController.navigate(Screen.NotesList.route) {
                        popUpTo(Screen.Splash.route) { inclusive = true }
                    }
                }
            )
        }

        composable(Screen.NotesList.route) {
            NotesListScreen(
                viewModel = viewModel,
                onNoteClick = { noteId ->
                    navController.navigate(Screen.ViewNote.createRoute(noteId))
                },
                onAddNoteClick = {
                    navController.navigate(Screen.AddNote.route)
                }
            )
        }

        composable(Screen.AddNote.route) {
            AddNoteScreen(
                viewModel = viewModel,
                onNavigateBack = {
                    navController.popBackStack()
                }
            )
        }

        composable(
            route = Screen.ViewNote.route,
            arguments = listOf(navArgument("noteId") { type = NavType.LongType })
        ) { backStackEntry ->
            val noteId = backStackEntry.arguments?.getLong("noteId") ?: 0L
            ViewNoteScreen(
                noteId = noteId,
                viewModel = viewModel,
                onNavigateBack = {
                    navController.popBackStack()
                }
            )
        }
    }
}
