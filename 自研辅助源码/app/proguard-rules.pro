# Python/Chaquopy resolves the narrow port methods by their names.
-keep class com.example.dwpmclone.host.AndroidSharedCorePortBridge { public *; }
-keep class com.example.dwpmclone.host.SharedPythonCoreHost { public *; }
-keepclassmembers class * { @android.webkit.JavascriptInterface <methods>; }
-keepattributes Signature,InnerClasses,EnclosingMethod
