# Alpha 5 Package System

## Package manifest

```yaml
name: android
version: 0.1.0
description: Android debugging and APK workflow package
capabilities:
  - android_debug
  - apk_build
commands:
  - android.doctor
drivers:
  - adb
permissions:
  - filesystem
  - shell_limited
policies:
  - human_gate_for_publish
```

## Rules

- Packages declare capabilities.
- Packages do not directly call model providers.
- Packages must declare permissions.
- Packages can declare drivers and policies.
- Install writes a package receipt.
