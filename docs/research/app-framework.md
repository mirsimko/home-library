# Research: framework and toolchain for the family app

Provenance: produced on 2026-10-13 by the deep-research-routed workflow (Sonnet searches and fetches, claims checked by two Opus 5.5 votes and one GPT-6.1 Sol vote, synthesis by Opus 5.5). Web sources only; nothing here was tried on the family's devices.


Verified with 3-vote adversarial checking (2 Opus + 1 GPT-6.1 Sol). 25 claims checked, 20 confirmed, 5 refuted.

## Summary

I recommend one Python-served web app (FastAPI with server-rendered pages) for every device. The iPad and laptop use it in the browser for review and correction, and the two Android phones install it as a PWA for capture. This avoids Apple's toolchain, the $99 fee and the question of using the employer's account. The main verified PWA weakness is that iOS has no Background Sync or Background Fetch, so queued uploads only run while the app is open. That barely matters here, because capture happens on Android and the iPad only reviews. If capture through the browser turns out to be inadequate on the phones, the fallback is an Expo (React Native) app. Expo is the only verified first-party way to build and ship iOS without a Mac (EAS Build and EAS Submit), and its Android APKs can be sideloaded with no store account. Any iOS build should then use a personal $99/yr account rather than the employer's team, and TestFlight builds have to be re-uploaded every 90 days. Python-native mobile clients (Flet, Toga, Kivy/BeeWare) are not recommended: building them for iOS still needs macOS runners, and their table widgets are too immature for a review screen. The back end would be FastAPI with photos on local disk, a SQLite database, and a job table claimed by a separate worker process that runs the two GPT-6.1 Sol reads through Codex. The build plan is phased and starts with the spec's existing no-client path: phone photos go into a shared cloud folder, and the store (Grist) is used for review.

## Findings

### [high] Expo's EAS Build compiles iOS apps on Expo's own hosted macOS machines, so a developer on Windows or Linux (including WSL2) can produce iOS builds without owning a Mac or running Xcode.

Seven claims were merged here, all voted 3-0. Expo's article (published Oct 7, 2026) states: "iOS builds from any operating system". The EAS docs say iOS builds run in a fresh macOS VM on Mac mini hosts in Expo's own cloud. The command is `eas build --platform ios`, and Expo's September 2026 material says the CLI runs in WSL. Expo also states that Xcode and the iOS Simulator are macOS-only and that you can still build and test from Windows or Linux in three ways, each with its own cost. Limits: the free plan's builds wait in a low-priority queue, and the simulator cannot test the camera. The older 'managed workflow' wording now means Continuous Native Generation with config plugins.

Sources: https://expo.dev/articles/testing-and-previewing/test-ios-app-without-mac, https://expo.dev/articles/testing-and-previewing, https://docs.expo.dev/build/introduction/, https://docs.expo.dev/build-reference/infrastructure/, https://vp0.com/blogs/do-i-need-mac-publish-ios-app.md, https://www.pkgpulse.com/guides/react-native-vs-flutter-vs-expo-2026, https://www.pkgpulse.com/guides/best-mobile-frameworks-2026, https://tech-insider.org/flutter-vs-react-native-2026/

### [high] EAS Submit uploads the build to App Store Connect and TestFlight from Windows or Linux, and EAS CLI can manage signing credentials. Shipping to an iPad that way still requires a paid Apple Developer account, and only an Account Holder or Admin can create the App Store Connect API key that EAS Submit uses.

The Expo docs say: "Both `eas build` and `eas submit` run on macOS, Linux, and Windows." Their FAQ answers "Do I need a Mac to distribute an app with TestFlight?" with no. They also say "A paid Apple Developer account is required to submit apps to the Apple App Store", and that EAS CLI handles certificates and provisioning profiles once you sign in to Apple. A Mac is needed only for the manual fallback upload. Votes were 3-0, and the blog sources agree with the primary docs.

Sources: https://docs.expo.dev/submit/testflight.md, https://docs.expo.dev/submit/ios/, https://docs.expo.dev/build/setup, https://axonbuild.com/blog/testflight-submission-vibe-apps/, https://vp0.com/blogs/do-i-need-mac-publish-ios-app.md

### [high] TestFlight internal testing covers up to 100 App Store Connect team members, needs no Beta App Review, and builds are available as soon as processing finishes. External testing covers up to 10,000 testers, and the first build of each version needs Beta App Review. Every build expires 90 days after upload with no way to extend it, and each tester can use up to 30 devices. A family app kept on TestFlight therefore needs a new upload at least every 90 days, even if the code has not changed.

Four claims were merged here, all voted 3-0. Apple's TestFlight overview says: "You can test a build for up to 90 days" and "Your build becomes unavailable for testers after 90 days". The TestFlight page says "Testers can access all available beta builds ... on up to 30 devices". An Apple Developer Forums thread from August 2026 confirms builds still expire exactly 90 days after upload. Apple adds that later builds of a version 'may not require a full review'. The only carve-out is for builds that go live on the App Store, which does not apply to a private family app.

Sources: https://docs.expo.dev/submit/testflight.md, https://developer.apple.com/testflight/, https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/, https://expo.dev/articles/testing-and-previewing/test-ios-app-without-mac, https://axonbuild.com/blog/testflight-submission-vibe-apps/

### [medium] Using the employer's Apple Developer Program team for this family app is a poor fit. Internal TestFlight testers must be users on that App Store Connect team, so the second adult would have to be added to the employer's team. EAS Submit also needs an Admin or Account Holder to create the API key. If a native iOS app is ever needed, a personal $99/yr account is the clean option. The web-app route needs no Apple account at all.

The team-membership and role requirements come from the verified claims and verifier notes (internal testers are 'Users on your App Store Connect team', and 'Only an Account Holder or Admin can create the App Store Connect API key'). The conclusion that personal use is inappropriate is a judgment. No source checked the employer's policy or Apple's terms on personal apps under an organisation account.

Sources: https://docs.expo.dev/submit/testflight.md, https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/, https://expo.dev/articles/testing-and-previewing/test-ios-app-without-mac

### [medium] Expo can also share an app without TestFlight. You install an ad hoc iOS build or an Android APK once, then ship JavaScript and asset changes as over-the-air updates. On Android this needs no store account at all, because the APK installs from a URL. Ad hoc on iOS still needs the paid Apple account and registered devices, and any change to native code needs a new build.

Voted 3-0. Expo says: "install an ad hoc iOS build or Android APK once, send JavaScript changes as updates, or use a hosted simulator." The internal-distribution docs confirm ad hoc provisioning, device UDID registration with `eas device:create`, and APK install from a URL. A separate claim about ad hoc limits ('capped at 100 devices per account per year, and new device registration can take 24 to 72 hours') was refuted 0-3, so treat those details as unverified.

Sources: https://expo.dev/articles/testing-and-previewing, https://docs.expo.dev/build/internal-distribution/

### [medium] At family scale, the only unavoidable cost on the no-Mac Expo path is the Apple Developer account at $99/yr. EAS has a $0 Free plan with 15 iOS and 15 Android builds a month on a low-priority queue, and sideloaded Android APKs avoid Google Play's $25 fee.

Voted 2-1. The vp0 blog (2026-08-09) says: "everything is $0 until the Apple developer account". Expo's pricing confirms the free tier. The dissent and caveats: free-tier queues can run 90 minutes or more at peak, heavier use pushes you to Starter at $19/month, and Expo Go on an iPad runs compatible projects with only a free Expo account, but as a development workflow tied to a running dev server rather than a durable install. Hosting and LLM costs are outside this claim.

Sources: https://vp0.com/blogs/do-i-need-mac-publish-ios-app.md, https://expo.dev/pricing, https://docs.expo.dev/billing/plans

### [medium] Flutter, Capacitor/Ionic and native projects need a macOS environment for iOS builds, either a Mac or hosted macOS CI. Hosted services exist (Codemagic for Flutter; Capawesome, Capgo or Ionic Appflow for Capacitor), but they are third-party add-ons, whereas Expo builds this into its own toolchain. Debugging on a simulator or device still needs a Mac.

Voted 2-1. The axonbuild post (updated 2026-09-06) says: "Capacitor, Flutter, and native projects need a macOS environment, either a hosted CI service with macOS runners or a Mac." Codemagic's and Capgo's guides corroborate this. The dissent: 'unlike Expo' is loose, because EAS also runs on Macs and Expo simply hosts them. xtool builds SwiftPM iOS apps on Linux or WSL, but it lacks most entitlements and asset catalogs, so it is niche. No verified claims covered .NET MAUI or Compose Multiplatform. Both build iOS through Xcode and so would face the same need for a Mac or macOS CI; that point is inferred, not verified.

Sources: https://axonbuild.com/blog/testflight-submission-vibe-apps/, https://github.com/xtool-org/xtool

### [medium] iOS and iPadOS PWAs support none of Background Sync, Periodic Background Sync or Background Fetch as of October 2026. An offline photo queue in an iOS PWA can therefore only upload while the app is open. That is acceptable here, because capture runs on the Android phones and the iPad only reviews and corrects.

Voted 2-1. The firt.dev notes (a 2023 snapshot) mark all three APIs unsupported. caniuse, current for iOS 27.1–27.2 and Safari 27.1 TP, still shows them unsupported. The usual workaround is to queue in IndexedDB and drain the queue when the app opens. Not verified here: a separate claim about PWA camera access ('getUserMedia ... from iOS 13 and file input works from iOS 6') was refuted 0-3, and no claim checked Android Chrome's Background Sync, BarcodeDetector support or camera quality. Applying the iOS limit to this family's device split is a judgment.

Sources: https://firt.dev/notes/pwa-ios/, https://caniuse.com/background-sync, https://caniuse.com/mdn-api_backgroundfetchmanager

### [medium] Python-native clients are weak choices for this app. Flet does build native mobile packages (`flet build apk/aab/ipa`), but its iOS build runs on a macOS runner. Toga is easy to use, but its widgets are crude: its Table widget has no iOS support and only beta support on Android, which rules out a record-review grid on the iPad. The Kivy and BeeWare comparison articles found were marketing or out of date. The practical way to keep the client in Python is a Python-served web app (FastAPI or NiceGUI pages) rather than a packaged mobile app.

Three claims were merged here (votes 2-0, 3-0 and 3-0). Flet's docs list apk, aab, ipa and ios-simulator targets, and their GitHub Actions example builds the ipa on macos-26. That refutes a dev.to table that put Flet on 'mobile via web'. A 2024 blog author found "Toga turned out to be much simpler to use than even Flet" but reported crude data tables and a hard-to-build Reset button. Toga's current docs confirm the Table limits. The SynapseIndia Kivy-vs-BeeWare piece is a sales page that never mentions camera, barcode, building without a Mac, or background upload. No verified claims covered NiceGUI or Streamlit. Recommending a web-served Python UI is a judgment drawn from these facts.

Sources: https://flet.dev/docs/publish, https://dev.to/arseytech/flet-vs-kivy-which-one-should-you-use-for-your-next-python-gui-app-2ak4, https://planandmanage.substack.com/p/beeware-it-is-my-android-learning, https://toga.beeware.org/en/stable/reference/api/widgets/table/, https://dev.to/synapseindia/kivy-vs-beeware-best-python-frameworks-for-ios-app-development-229a

### [medium] The back end is FastAPI with SQLite and a job table. An upload writes the photo to disk and inserts a PENDING job. A separate worker process claims jobs atomically: it opens a BEGIN IMMEDIATE transaction, then runs a conditional UPDATE ... WHERE status='PENDING' and checks the row count. It then runs the reading pipeline, handing the photo to GPT-6.1 Sol via Codex. No Redis or Celery is needed. The stuck-job timeout must be well above the length of a reading session, or the job needs a heartbeat.

Voted 2-1. The qq README describes "A job queue built with FastAPI + SQLite where background workers poll, claim, and execute jobs atomically". It polls every 500 ms, retries with exponential backoff, and runs a sweep every 30 s that marks jobs stuck for more than 5 minutes as FAILED. The repo is a hobby project (0 stars, no license), so it shows the pattern but not production maturity. huey's SqliteStorage and litequeue are established equivalents. The project spec says each Sol/Codex session takes about 3 minutes and each photo is read twice. qq's 5-minute timeout would therefore re-run jobs, so raise it or add heartbeats. Storing photos on local disk under content-hash names, with the paths in SQLite, is a judgment and was not verified.

Sources: https://github.com/mo1ein/qq

### [low] Recommended stack: a FastAPI back end with Jinja/HTMX server-rendered pages, SQLite, photos on disk, and a SQLite job queue plus a separate worker process that runs the Codex/Sol reading pipeline. The same web app runs in Safari on the iPad and in a laptop browser for review, and is installed as a PWA on the Android phones for capture. Escalate to an Expo (React Native) Android app, sideloaded as an APK, only if web capture fails. Add iOS through EAS only if a native iPad app proves necessary, and then on a personal Apple account.

This recommendation combines the verified findings with judgments that were not verified. Verified: Expo is the only first-party no-Mac iOS path; TestFlight brings Apple-account overhead and 90-day expiry; Python-native mobile frameworks have iOS and widget limits; the iOS PWA limit does not affect Android capture. Unverified assumptions: Android Chrome's camera capture through `<input type=file accept=image/* capture=environment>` keeps full photo quality, an IndexedDB upload queue is reliable enough on the phones, and ISBN barcodes can be decoded on the server from the barcode photo (e.g. zxing-cpp) or on the device with a JS library. A single Python codebase suits a mobile beginner whose AI agents write the code, and it keeps the client inside the developer's preferred language. Expo's barcode scanning and background-upload quality were not verified.

Sources: https://docs.expo.dev/submit/testflight.md, https://expo.dev/articles/testing-and-previewing, https://firt.dev/notes/pwa-ios/, https://flet.dev/docs/publish, https://toga.beeware.org/en/stable/reference/api/widgets/table/, https://github.com/mo1ein/qq

### [low] Phased build plan. Phase 0, no custom client: follow the spec's path. Android camera photos go into a shared cloud folder with one sub-folder per location, a harness job reads them with Sol, and Grist or Sheets serves as both store and review view. Run the planned store test, and stop if Grist's UI works for review on the iPad. Phase 1, back end: FastAPI upload endpoint (photo, kind = cover/barcode/shelf, location), photos on disk, SQLite tables for photos, books, locations and jobs, and the worker pipeline (tile and rotate shelf photos, two independent Sol reads, compare them, look up ISBNs by language, write the record with needs_review set), built test-first. Phase 2, web client: a capture page (location picker, camera input, IndexedDB queue with retry) and a keyboard-friendly review page (photo beside editable fields, a control to clear the review flag), plus search; install as a PWA on Android. Phase 3: remote access, backups and spreadsheet export. Phase 4, only if needed: an Expo Android capture app through EAS, and iOS only on a personal account.

The plan is a synthesis, not a verified claim. Phase 0 comes from the repository's own spec (/mnt/data/dev/home-library/docs/spec.md, sections 2.6–2.7 and requirement R7, 'A plain spreadsheet is an acceptable end state'). The pipeline steps in Phase 1 come from spec section 2.4 (tiling, 180-degree copies, two blind reads, about 3 min per Sol session) and section 2.5 (ISBN sources by language). The later phases order the escalation path so that no Apple account is needed unless a native app is ever required.

Sources: https://github.com/mo1ein/qq, https://firt.dev/notes/pwa-ios/, https://expo.dev/articles/testing-and-previewing

## Caveats
The verified evidence is thin on several parts of the question. No claim that survived verification covered:
- PWA camera quality on Android, or Android Chrome's Background Sync and BarcodeDetector support. The one camera claim, about getUserMedia and file input on iOS, was refuted 0-3.
- How well barcodes scan in each framework (expo-camera, Flutter plugins, JS libraries).
- React Native vs Flutter maturity, .NET MAUI, Kotlin/Compose Multiplatform, NiceGUI, or Streamlit.
- Home vs cloud hosting, remote access, or two-user authentication.

The recommended stack and the phased plan are therefore judgment built on a narrow verified base. They should be tested hands-on before being committed to.

Source quality:
- The Expo facts come from Expo itself, so they are self-interested. Apple's documentation and several independent blogs corroborate them.
- The Flet, Toga and Kivy evidence is a 2024 personal blog plus vendor docs.
- The SQLite queue example is a hobby repository.
- The iOS PWA claim depends on a 2023 snapshot, though current caniuse data confirms it.

Two refuted claims should not be relied on:
- 'Ad hoc is capped at 100 devices per year, and device registration can take 24–72 hours.'
- 'Any physical-device iOS build needs a paid account.' The likely counterexample is Expo Go running development projects on an iPad, which is not a durable install.

Time sensitivity: Apple's TestFlight rules (90-day expiry, tester limits), EAS free-tier quotas and pricing, and Safari's PWA feature support all change from year to year. They were checked as of 2026-10-13.

## Open questions
- How well does a browser-based capture flow work on the family's actual Android phones? This covers full-resolution photos from the camera file input, whether an IndexedDB upload queue survives the app being closed, Chrome Background Sync, and whether on-device ISBN scanning in the browser (BarcodeDetector or a JS library) is reliable. Or is it simpler to decode barcodes on the server from the barcode photo?
- Does the custom back end become the catalog store (SQLite with its own review UI), or does it only run the reading pipeline and write records into Grist or Sheets, whose own UI serves as the review view? The spec's planned store test should settle whether a custom review page is needed at all.
- Where should the back end and the Codex/Sol worker run: an always-on home machine on the existing Codex subscription, or a small cloud VM? How should the two adults reach it away from home (a private overlay network or a public endpoint with login), given the spec's finding that long reading sessions overload the home uplink?
- Does the employer's Apple Developer Program agreement or policy allow a personal family app on its team at all? And does any requirement (such as offline capture on the iPad) actually justify a native iOS app over the web app?

## Refuted claims
- (0-3) Any build that runs on a physical iPhone/iPad needs a paid Apple Developer account ($99/yr) for signing; only simulator builds avoid it. — https://expo.dev/articles/testing-and-previewing/test-ios-app-without-mac
- (0-3) getUserMedia camera access works in iOS PWAs from iOS 13 and file input works from iOS 6, but advanced camera controls are unsupported. — https://firt.dev/notes/pwa-ios/
- (1-2) Kivy is more established than BeeWare, which the article says was still in development when it was written. This is dated and not verified for 2026. — https://www.monterail.com/blog/python-for-mobile-app-development
- (0-3) Python is not native to iOS or Android, so deployment can be slow and difficult. This is a generic claim with no 2026 data on building for iOS without a Mac. — https://www.monterail.com/blog/python-for-mobile-app-development
- (0-3) Ad hoc distribution is capped at 100 devices per account per year, and new device registration can take 24 to 72 hours (first build may fail until then). — https://expo.dev/articles/testing-and-previewing/test-ios-app-without-mac
