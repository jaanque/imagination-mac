# CloudSwiftApp

Build native **Swift** and **SwiftUI** apps for **iOS** and **macOS** from **Windows or Linux**—without owning a Mac—using **XcodeGen** and **GitHub Actions** (`macos-latest`).

---

## How It Works

1. You write Swift & SwiftUI code on Windows or Linux (e.g., in VS Code).
2. **`project.yml`** defines the iOS (`17.0+`) and macOS (`14.0+`) app targets declaratively.
3. On every push to `main` (or manual run via `workflow_dispatch`), **GitHub Actions** spins up a cloud macOS runner, generates `CloudSwiftApp.xcodeproj` with **XcodeGen**, and compiles:
   - **`CloudSwiftApp-iOS-unsigned.ipa`** — Unsigned iOS app package ready for sideloading onto a physical iPhone/iPad.
   - **`CloudSwiftApp-iOS-Simulator.zip`** — Simulator build ready to run in browser-based iOS emulators like Appetize.io.
   - **`CloudSwiftApp-macOS.dmg`** — Unsigned macOS disk image installer.
4. Pushing a version tag (e.g., `v1.0.0`) automatically publishes a **GitHub Release** with all three artifacts attached.

---

## Getting Started (Step-by-Step)

### 1. Create Your Repository
1. Click **Use this template** at the top of this repository on GitHub and create a new repository.
2. Clone your new repository to your Windows or Linux machine:
   ```bash
   git clone https://github.com/<your-username>/<your-repo>.git
   cd <your-repo>
   ```

### 2. Set Up VS Code
1. Open the folder in **Visual Studio Code**.
2. Install the official **[Swift](https://marketplace.visualstudio.com/items?itemName=sswg.swift-lang)** extension (`sswg.swift-lang`) for syntax highlighting and Swift language support.
3. Edit `Sources/ContentView.swift` (for example, change the text or button label).

### 3. Trigger Your First Cloud Build
Commit and push your changes to `main`:
```bash
git add .
git commit -m "Customize CloudSwiftApp UI"
git push origin main
```
Or trigger a build manually without pushing code:
1. Go to the **Actions** tab in your GitHub repository.
2. Select **Build CloudSwiftApp**.
3. Click **Run workflow** and choose `all`, `ios`, or `macos`.

Once the workflow finishes, download your compiled artifacts from the **Artifacts** section at the bottom of the workflow run summary.

---

## Adding Files & Swift Packages (`project.yml`)

### Adding New `.swift` Files or Assets
Any `.swift` file placed inside `Sources/` and any asset added to `Resources/Assets.xcassets/` is automatically included in both iOS and macOS targets—no manual `.xcodeproj` edits required.

### Adding Swift Package Manager (SPM) Dependencies
Open `project.yml` and add a `packages` block at the root, then link the dependency inside your target(s):

```yaml
packages:
  Alamofire:
    url: https://github.com/Alamofire/Alamofire.git
    from: 5.9.0

targets:
  CloudSwiftApp-iOS:
    # ... existing configuration ...
    dependencies:
      - package: Alamofire
```

---

## Installing the `.ipa` on a Physical iPhone (Windows / Linux)

Because this template builds without a paid Apple Developer account, the `.ipa` is unsigned. You can install it on your own iPhone or iPad using a **free Apple ID** with one of these tools:

- **[Sideloadly](https://sideloadly.io/)** (Windows & macOS)
  1. Download `CloudSwiftApp-iOS-unsigned.ipa` from GitHub Actions Artifacts and unzip it.
  2. Connect your iPhone via USB, open Sideloadly, drag in the `.ipa`, enter your Apple ID, and click **Start**.
  3. On your iPhone, go to **Settings > General > VPN & Device Management** and trust your developer profile.
- **[AltStore](https://altstore.io/)** (Windows & Linux via AltServer)
  1. Install AltServer on your computer and AltStore on your iPhone.
  2. Transfer the `.ipa` to your iPhone and open it in AltStore to sign and install it.

> **7-Day Renewal Note:** Apps signed with a free Apple ID expire after **7 days** and must be re-signed (AltStore can refresh them automatically over Wi-Fi when your computer is on the same network).

---

## Testing in Your Browser Without an iPhone (Appetize.io)

If you do not have an iPhone available, you can test the iOS build directly in your browser:
1. Download **`CloudSwiftApp-iOS-Simulator.zip`** from the GitHub Actions run artifacts.
2. Unzip it once if GitHub Actions wrapped it in an outer artifact zip so you have `CloudSwiftApp-iOS-Simulator.zip` (containing `CloudSwiftApp-iOS.app`).
3. Upload `CloudSwiftApp-iOS-Simulator.zip` to **[Appetize.io](https://appetize.io/)** (which offers a free tier for testing) to launch an interactive iOS simulator in your browser.

---

## GitHub Actions Minutes Warning

- **Public repositories:** GitHub Actions minutes on `macos-latest` are **unlimited and free**.
- **Private repositories:** GitHub applies a **10x minute multiplier** to macOS runners (1 minute on `macos-latest` consumes 10 minutes of your monthly free quota). Keep your repository public while learning, or use the `platform` input on `workflow_dispatch` to build only `ios` or `macos` when testing in private repos.

---

## Optional: Adding Official Code Signing (Paid Apple Developer Account)

If you enroll in the Apple Developer Program (\$99/year) and want signed App Store / TestFlight / notarized builds:

1. Export your distribution certificate as a `.p12` file and download your `.mobileprovision` profile from the Apple Developer portal.
2. Base64-encode both files and store them in **Settings > Secrets and variables > Actions**:
   - `APPLE_CERTIFICATE_BASE64`
   - `APPLE_CERTIFICATE_PASSWORD`
   - `PROVISIONING_PROFILE_BASE64`
3. Update `.github/workflows/build.yml` to import the certificate into a temporary macOS keychain, install the provisioning profile into `~/Library/MobileDevice/Provisioning Profiles/`, and remove the `CODE_SIGNING_ALLOWED=NO` flags from `xcodebuild`.
