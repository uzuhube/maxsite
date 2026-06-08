package com.maxsite.notes

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.navigation.compose.rememberNavController
import com.maxsite.notes.ui.navigation.NavGraph
import com.maxsite.notes.ui.screens.NotesViewModelFactory
import com.maxsite.notes.ui.theme.NotesTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val application = application as NotesApplication
        val viewModelFactory = NotesViewModelFactory(application.repository)

        setContent {
            NotesTheme {
                val navController = rememberNavController()
                NavGraph(
                    navController = navController,
                    viewModelFactory = viewModelFactory
                )
            }
        }
    }
}
