package com.example.dwpmclone

import android.app.Application
import com.example.dwpmclone.host.SharedPythonCoreHost

/** Starts the shared interpreter off the UI thread so local calls stay responsive. */
class SharedCoreApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        SharedPythonCoreHost.get(this).warmUpAsync()
    }
}
