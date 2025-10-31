# Installing Google Cloud SDK (gcloud)

Since you're on macOS, here are several ways to install gcloud:

## Method 1: Using Homebrew (Easiest)

If you have Homebrew installed:

```bash
brew install google-cloud-sdk
```

**Note:** If you get an Xcode license error, you may need to:
```bash
sudo xcodebuild -license accept
```

Then try again.

## Method 2: Manual Installation Script

1. Download and run the installer:
```bash
curl https://sdk.cloud.google.com | bash
```

2. Restart your shell or reload your profile:
```bash
exec -l $SHELL
```

3. Initialize gcloud:
```bash
gcloud init
```

## Method 3: Using the Interactive Installer

1. Download the macOS installer from:
   https://cloud.google.com/sdk/docs/install

2. Run the downloaded `.pkg` file and follow the installation wizard

3. Open a new terminal window

4. Initialize:
```bash
gcloud init
```

## After Installation

1. **Authenticate:**
```bash
gcloud auth login
```

2. **Set your project:**
```bash
gcloud config set project lancelot-fa22c
```

3. **Enable required APIs:**
```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

4. **Verify installation:**
```bash
gcloud --version
```

## Alternative: Deploy via Cloud Console

If you prefer not to install gcloud, you can also:

1. Build and push the Docker image manually using Docker
2. Deploy through the Google Cloud Console web interface at:
   https://console.cloud.google.com/run

## Alternative: Use Cloud Build UI

You can also use the Cloud Build interface in the console to build and deploy:
https://console.cloud.google.com/cloud-build

