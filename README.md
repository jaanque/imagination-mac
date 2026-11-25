# Cloud Swift Builder

Compile Swift and SwiftUI apps for **iOS** (`.ipa` + Simulator `.zip`) and **macOS** (`.dmg`) directly on GitHub Actions — **100% free, zero external servers, and no local Mac required**.

Built for developers on **Windows** and **Linux** who want to build, sideload, or test SwiftUI apps using only a GitHub repository.

---

## Quick Start (3 Steps)

1. **Zip your project** (max **25 MB**, GitHub's native issue attachment limit).
   - Want to test immediately? Zip the contents of [`sample-app/`](sample-app/) (e.g., `Sources/` and `project.yml`).
2. **Open a Build Request**:
   - Go to the **Issues** tab → **New Issue** → **Build Swift App (iOS / macOS)**.
   - Drag and drop your `.zip` file into the **Project Archive (.zip)** field, choose your **Target Platform**, and click **Submit new issue**.
3. **Download your binaries**:
   - Wait ~2–4 minutes for GitHub Actions to finish compiling on `macos-latest`.
   - The bot will comment on your issue with direct download links (or the last 60 lines of the `xcodebuild` error log if compilation failed) and automatically close the issue.

---

## Supported `.zip` Project Structures

The build engine automatically detects how your archive is organized:

### 1. XcodeGen (`project.yml`)
Include a `project.yml` file at the root of your `.zip`:
```text
my-app.zip
├── project.yml
└── Sources/
    ├── App.swift
    └── ContentView.swift
```

### 2. Existing Xcode Project (`.xcodeproj` or `.xcworkspace`)
Include your existing Xcode project or workspace:
```text
my-app.zip
├── MyApp.xcodeproj/
└── MyApp/
    ├── MyAppApp.swift
    └── ContentView.swift
```
The primary application scheme is detected automatically via `xcodebuild -list -json`.

### 3. Standalone `.swift` Files
No `project.yml` or `.xcodeproj`? Just zip your `.swift` files:
```text
my-app.zip
├── App.swift
└── ContentView.swift
```
Optionally provide **App Name** and **Bundle Identifier** in the issue form; the builder will generate a valid XcodeGen project targeting iOS 17.0 / macOS 14.0 automatically.

---

## Installing the `.ipa` on iPhone / iPad (Windows & Linux)

Because builds are compiled **unsigned** (`CODE_SIGNING_ALLOWED=NO`), you can sign and install the `.ipa` onto your own device using a **free Apple ID**:

- **Windows (Sideloadly)**:
  1. Download `*-iOS-unsigned.ipa` from the issue comment.
  2. Open [Sideloadly](https://sideloadly.io/), connect your iPhone via USB, drag in the `.ipa`, enter your Apple ID, and click **Start**.
  3. On your iPhone, go to **Settings → General → VPN & Device Management** and trust your developer profile.
- **Windows (AltStore)** / **Linux (AltServer / SideStore)**:
  - Use AltServer/AltStore to sideload the `.ipa` with your free Apple ID.

> **Note:** Apps signed with a free Apple ID remain valid for 7 days before needing a quick refresh.

---

## Testing in the Browser with Appetize.io (No iPhone Needed)

When you select **iOS** or **Both**, the workflow also produces `*-iOS-Simulator.zip`.
1. Download `*-iOS-Simulator.zip` from the issue comment.
2. Upload it to [Appetize.io](https://appetize.io) to run and interact with your iOS app directly in any web browser on Windows or Linux.

---

## Security & Retention Architecture

Compiling third-party Swift projects runs arbitrary code (`xcodebuild`, Swift macros, build scripts). This repository isolates untrusted execution using a strict 3-job pipeline:

1. **`validate` (`ubuntu-latest`, `permissions: { issues: read }`)**:
   - Parses the issue form with `scripts/parse_issue.py`.
   - Enforces **SSRF protection**: only `https://github.com/` and `https://objects.githubusercontent.com/` attachment URLs are accepted.
   - Sanitizes `app_name` and `bundle_id` inputs.
2. **`compile` (`macos-latest`, `permissions: {}`)**:
   - Runs with **zero GitHub token permissions**, ensuring no `GITHUB_TOKEN` privileges exist while compiling user code.
   - Checks out only `scripts/` with `persist-credentials: false`.
   - Downloads the `.zip` (capped at 35 MB) and extracts it with **Zip Slip**, **symlink**, and **zip-bomb** protections inside `/tmp/user_workspace`.
   - Uploads binaries and `build_report.md` (with internal paths redacted) as a 1-day workflow artifact.
3. **`deliver` (`ubuntu-latest`, `permissions: { contents: write, issues: write }`)**:
   - Publishes binaries to a temporary prerelease (`build-<issue>-<run_id>`), comments the download links (or build errors) on the issue, applies `build-success` / `build-failed`, and closes the issue.

### Automatic 7-Day Cleanup
The scheduled workflow [`.github/workflows/cleanup-releases.yml`](.github/workflows/cleanup-releases.yml) runs daily at `04:00 UTC` (and can be triggered manually) to delete all `build-*` releases and their Git tags older than **7 days**, keeping repository storage clean.
