# AutoSubtitle — Complete Distribution & Trust Guide

---

## The Big Picture

| Goal | Solution |
|---|---|
| Users get a single double-click installer | ✅ Inno Setup `.exe` |
| You never use a terminal after setup | ✅ GitHub Actions builds it for you |
| Windows SmartScreen doesn't block it | ✅ SignPath.io free code signing |
| Downloads are free to host | ✅ GitHub Releases |

---

## PART 1 — One-Time Setup (do this once, never again)

### Step 1 — Install the two build tools

1. **Inno Setup 6** → https://jrsoftware.org/isinfo.php (free, ~5 MB)
2. **cx_Freeze**:
   ```
   pip install cx_freeze
   ```

### Step 2 — Build the exe folder

Open a terminal in the project folder:
```
python build_exe.py build
```
Creates: `build\exe.win-amd64-3.11\`

> If your Python version differs (e.g. 3.12), open `AutoSubtitle_Setup.iss`
> and update `#define BuildDir` at the top to match.

### Step 3 — Compile the installer

1. Open `AutoSubtitle_Setup.iss` in **Inno Setup Compiler**
2. Press **Ctrl+F9**
3. Done → `installer_output\AutoSubtitle_Setup.exe`

You now have a working installer. Everything below makes it trusted and automatic.

---

## PART 2 — GitHub Setup (host your releases for free)

### Step 1 — Create the repository

1. Go to https://github.com/new
2. Name it `autosubtitle` (or whatever you like)
3. Set it to **Public** (required for free SignPath signing)
4. Click **Create repository**

### Step 2 — Push your code

In the project folder:
```
git init
git add .
git commit -m "Initial release"
git remote add origin https://github.com/YOURUSERNAME/autosubtitle.git
git push -u origin main
```

### Step 3 — Create a Release

1. On GitHub, go to your repo → **Releases** → **Draft a new release**
2. Click **Choose a tag** → type `v1.0.0` → **Create new tag**
3. Title: `AutoSubtitle v1.0.0`
4. Drag your `AutoSubtitle_Setup.exe` into the assets box
5. Click **Publish release**

Your download URL will be:
```
https://github.com/YOURUSERNAME/autosubtitle/releases/latest/download/AutoSubtitle_Setup.exe
```

Share this link with anyone. GitHub serves it forever for free.

> **SmartScreen note:** GitHub-hosted releases build reputation over time.
> After ~20-50 unique downloads, SmartScreen stops showing a warning automatically.
> SignPath (Part 3) makes it trusted *immediately* from download #1.

---

## PART 3 — Free Code Signing with SignPath.io

SignPath offers **free code signing for open source projects**.
A signed installer gets instant SmartScreen trust — no reputation waiting period.

### Step 1 — Apply for the free OSS program

1. Go to https://signpath.io/product/open-source
2. Click **Apply for free**
3. Fill in:
   - **Project URL:** your GitHub repo URL
   - **Description:** "Smart subtitle generator for Adobe Premiere Pro"
   - Confirm the project is open source and non-commercial
4. Wait for approval email (usually 1-3 business days)

### Step 2 — Set up your SignPath project (after approval)

1. Log into https://app.signpath.io
2. Create a new **Project** called `AutoSubtitle`
3. Under **Artifact Configurations**, create one with:
   - Type: `PE` (Windows executable)
   - File: `AutoSubtitle_Setup.exe`
4. Under **Signing Policies**, create a `release` policy
5. Generate an **API token**: go to your profile → **API Tokens** → **Generate**
6. Copy the token — you'll add it to GitHub next

### Step 3 — Add the token to GitHub

1. In your GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `SIGNPATH_API_TOKEN`
4. Value: paste your SignPath API token
5. Also add `SIGNPATH_ORGANIZATION_ID` (find this in SignPath under Organization Settings)

---

## PART 4 — GitHub Actions (automatic build + sign on every release)

Create this file in your repo at `.github/workflows/release.yml`.
Every time you push a tag like `v1.0.1`, GitHub builds the installer,
signs it via SignPath, and uploads it to your Release automatically.
You never open a terminal again.

```yaml
name: Build and Release

on:
  push:
    tags:
      - 'v*'   # triggers on v1.0.0, v1.2.3, etc.

jobs:
  build:
    runs-on: windows-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install build dependencies
        run: pip install cx_freeze

      - name: Build exe folder
        run: python build_exe.py build

      - name: Install Inno Setup
        run: |
          choco install innosetup --yes --no-progress
        shell: powershell

      - name: Compile installer
        run: |
          & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" AutoSubtitle_Setup.iss
        shell: powershell

      - name: Upload unsigned installer as artifact
        uses: actions/upload-artifact@v4
        with:
          name: unsigned-installer
          path: installer_output\AutoSubtitle_Setup.exe

      - name: Sign with SignPath
        uses: signpath/github-action-submit-signing-request@v1
        with:
          api-token: ${{ secrets.SIGNPATH_API_TOKEN }}
          organization-id: ${{ secrets.SIGNPATH_ORGANIZATION_ID }}
          project-slug: autosubtitle
          signing-policy-slug: release
          artifact-configuration-slug: installer
          github-artifact-id: unsigned-installer
          wait-for-completion: true
          output-artifact-directory: signed_output

      - name: Upload signed installer to GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: signed_output\AutoSubtitle_Setup.exe
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### How to publish a new version after this is set up

1. Update `AppVersion` in `AutoSubtitle_Setup.iss`
2. Commit your changes:
   ```
   git add .
   git commit -m "Release v1.0.1"
   git tag v1.0.1
   git push && git push --tags
   ```
3. GitHub builds it, SignPath signs it, it appears on your Releases page.
   **You never open Inno Setup or a terminal for building again.**

---

## Summary — What Each User Sees

1. They visit your GitHub Releases page (or you send them the direct link)
2. They download `AutoSubtitle_Setup.exe`
3. They double-click it — **no SmartScreen warning** (signed)
4. Standard wizard: Next → Next → Install
5. Python + all packages install silently if missing
6. Desktop shortcut + Start Menu with your icon
7. Finish → app launches

Zero terminal. Zero manual steps. Zero AV flags.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `BuildDir` not found | Update `#define BuildDir` in the `.iss` to match your Python version folder |
| SignPath approval takes long | You can release unsigned first; SmartScreen clears after ~50 downloads |
| GitHub Actions fails on Inno Setup step | Make sure `AutoSubtitle_Setup.iss` is in the repo root |
| Torch download is slow for users | It's ~800 MB CPU-only; GPU users can reinstall with CUDA URL after |
