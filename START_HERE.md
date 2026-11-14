# Start here: run EnergiQ AI on Windows

**Three steps:** extract the ZIP, double-click **`RUN_PROJECT.bat`**, and the application opens in your browser.

This page is for someone who has never run the project. Nothing here needs Docker, a database server or administrator rights, and after the first start it works without internet.

> **Honest note.** `RUN_PROJECT.bat`, `STOP_PROJECT.bat` and `CHECK_ENVIRONMENT.bat` have **not been run on a real Windows computer**; the workspace they were prepared in is Linux, and no Windows machine or emulator was available. What was done instead: the launcher they start (`run_energiq.py`) was run for real from a clean copy of the ZIP on Linux (first start, second start refused, status, stop), and its Windows-specific branches are unit-tested with the system calls replaced by test doubles. The three `.bat` files were checked for structure (CRLF line endings, ASCII only, every jump target defined, no administrator elevation) and their control flow was followed by a small simulator on simulated computers (no Python, an unsupported Python, ZIP not extracted, unusable folder, launcher failing, and so on). That is evidence the logic is right, not proof that `cmd.exe` accepts every line. If something fails on your computer, the [troubleshooting](#when-something-goes-wrong) table lists the likely causes, and the manual route in [section 7](#7-the-same-thing-by-hand-vs-code-and-powershell) does the same thing without the `.bat` files.

---

## 1. What you need (one time)

| Tool | Version | How to check | Where to get it |
|---|---|---|---|
| Python | 3.11 (3.12 and 3.13 also accepted) | open PowerShell, type `py -3.11 --version` | https://www.python.org/downloads/ . In the installer, **tick "Add python.exe to PATH"**. |
| Node.js (includes npm) | 20.19 or newer (22 LTS recommended) | `node --version` | https://nodejs.org/ (LTS) |
| Free disk space | about 4 GB | - | Python packages ~1.5 GB, web packages ~0.2 GB, the project ~0.5 GB |
| Internet | first start only | - | to download the Python and web packages once |

You do **not** need Git, Docker or PostgreSQL. `RUN_PROJECT.bat` cannot install Python or Node.js for you (that would need administrator rights); if one is missing it says which and where to get it.

Not sure what you have? Double-click **`CHECK_ENVIRONMENT.bat`**. It checks Python, Node.js, npm, the project files, free disk space, whether the folder can be written to, and whether ports 8000 and 5173 are free. It installs nothing and changes nothing.

## 2. Unpack the ZIP properly

1. Save `EnergiQ-AI-Professional-Final.zip` somewhere with a **short path**, for example `C:\EnergiQ`. Avoid OneDrive, Desktop and Documents folders that sync, and very long folder names: Windows can fail on long paths, and sync tools lock files while the packages install. Do not use a network drive.
2. **Right-click the ZIP, choose Properties, tick "Unblock" at the bottom, click OK.** (If you do not see "Unblock", skip this.) This removes the "downloaded from the internet" mark that makes Windows distrust the scripts inside.
3. **Right-click the ZIP, choose "Extract All..."** and extract to `C:\EnergiQ`. Do not run files from inside the ZIP window.

You should now have a folder such as `C:\EnergiQ\EnergiQ-AI` that contains `RUN_PROJECT.bat`, `STOP_PROJECT.bat`, `CHECK_ENVIRONMENT.bat`, `README.md`, `backend`, `frontend` and more.

## 3. Start it

Double-click **`RUN_PROJECT.bat`**. Do not use "Run as administrator"; it is not needed and would make the folder harder to use later.

A black window opens and prints each step as it happens:

1. **Checks your computer:** Python and Node.js (and npm). If one is missing or too old, it says which and stops with instructions.
2. **First start only:** creates a private Python environment (`.venv`; the launcher runs that environment's Python directly, so nothing has to be "activated") and installs the packages, then installs the web packages. This takes **3 to 10 minutes** depending on your internet. Later starts skip this, because the launcher remembers a fingerprint of the package lists and installs again only when they change.
3. **Prepares the database:** creates `data\energiq.db` and its tables if they do not exist, and keeps them between runs. It prints how many tables and user accounts there are.
4. **Starts the backend and the web app** and **waits until both really answer**. "Answer" means the backend reports its database is up, the web app serves the EnergiQ page, and the web app can reach the backend. It does not print the address before that.
5. **Loads the seven bundled communities** (first start only).
6. **Prints a box like this and opens your browser:**

```
================================================================
  EnergiQ AI is running:  http://127.0.0.1:5173
  Sign in with:           admin@example.com   /   <a password made for your copy>
  (This password is unique to this installation and is saved in .energiq-run\admin_login.txt.)
  API documentation:      http://127.0.0.1:8000/docs
  Keep this window open while you use the app. To stop: press Ctrl+C here, or run STOP_PROJECT.bat.
  Logs for troubleshooting: .energiq-run\launcher.log, backend.log, frontend.log
================================================================
```

If the ports are busy, the box shows the next free ones; use the address printed there.

**Keep that window open while you use the app.** Closing it stops the app.

**Starting twice is safe.** If EnergiQ AI is already running, a second double-click starts nothing new: it prints the address of the running copy and opens it. No duplicate backend or web app is ever started.

**Your sign-in password.** Every copy of the project makes its own random password on the first start. It is printed in the window and saved in `.energiq-run\admin_login.txt`. There is no shared default password, and the password is never written to the log files. To choose your own before the first start, set `ENERGIQ_ADMIN_PASSWORD` in PowerShell first (see section 7).

If a Windows Firewall pop-up appears for Python or Node, **Allow access on private networks** is fine; both servers listen on `127.0.0.1` (your own computer) only.

## 4. Stop it

* In the black window press **Ctrl+C**. Windows may then ask **"Terminate batch job (Y/N)?"**; press **Y**. Or
* double-click **`STOP_PROJECT.bat`**. It asks the running window to shut down, which ends that window cleanly with the message *stopped with STOP_PROJECT.bat*, and force-stops only what is still left. It touches only the backend, web app and launcher that were started from this folder, leaves alone a recorded process that no longer answers as EnergiQ (Windows can reuse process numbers), and does nothing if nothing is running. (If you stop it while the first-time setup is still installing packages, that window ends with an error code; that is expected.) Or
* close the black window.

Your data stays in `data\energiq.db`. Start again any time with `RUN_PROJECT.bat`.

## 5. Use it (a 5-minute tour)

Sign in, then follow the left menu.

| Page | What to look at |
|---|---|
| **Society overview** | Last 7 days of real demand and the next 24 hours forecast with its 80 % range, energy and cost cards. The blue note under the title says these are research data, not a live feed. |
| **Compare communities** | The seven communities side by side: energy per m², load factor, peak per m², forecast error. |
| **Consumption** | Total use of the community at hourly, daily, weekly and monthly resolution, with a table view of the same numbers. |
| **Forecasting** | Actual vs predicted on data the models never saw, error analysis (by hour, weekday and size), model comparison, and the "why" (SHAP). Try the horizon buttons. |
| **Buildings** | Compare buildings and open one for detail. |
| **Cost and peaks** | Peak demand, load-duration curve, distribution, and **tariffs**: add your own rate (flat or peak/off-peak, in your currency) and watch the cost change. |
| **Alerts** | Unusual-demand events found by the model. Acknowledge one (analyst or admin accounts). |
| **Recommendations / Reports** | Evidence-based advice; create and download a PDF or CSV report. |
| **Society admin** | (admin) import or delete communities, upload a meter file, train a model. |

Accounts made on the sign-in page ("Register") are analysts: they can acknowledge alerts and create reports. A **viewer** account is read-only by design; an administrator sets roles on the **Admin** page.

**Reading the numbers honestly.** The communities are real meter data of university and campus buildings from a public research data set (BDG2, 2016 to 2017), summed per hour. They are **not** family flats and **not** a registered housing society. The default tariff is labelled DEMO and is not a real utility price. The app says this on the pages where it matters.

## 6. What the three files are

| File | What it does | Changes anything? |
|---|---|---|
| `RUN_PROJECT.bat` | Finds a suitable Python and runs the launcher (`run_energiq.py`), which does steps 1 to 6 above | Creates `.venv`, `frontend\node_modules`, `data\energiq.db` and `.energiq-run` inside the project folder only |
| `STOP_PROJECT.bat` | Stops the copy that `RUN_PROJECT.bat` started | Ends only the processes recorded for this folder |
| `CHECK_ENVIRONMENT.bat` | Reports what is present and what is missing | No |

On macOS or Linux the same launcher is started with `./run_project.sh`, `./stop_project.sh` and `./check_environment.sh`.

## 7. The same thing by hand (VS Code and PowerShell)

Use this if you prefer to see every step, or if the `.bat` files are blocked on your computer.

Open the folder in VS Code (File, Open Folder), then Terminal, New Terminal (PowerShell):

```powershell
# the whole project with one command (same as RUN_PROJECT.bat)
py -3.11 run_energiq.py

# or step by step
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

$env:ENERGIQ_ENV = "dev"
$env:ENERGIQ_ADMIN_EMAIL = "admin@example.com"
$env:ENERGIQ_ADMIN_PASSWORD = "choose-a-long-password-1"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:create_app --factory --port 8000     # terminal 1

cd frontend
npm ci
npm run dev                                                                                  # terminal 2  -> http://localhost:5173
```

Then sign in with that email and password, open **Society admin**, click **Import bundled communities**, and wait for the Jobs page to say "succeeded".

If PowerShell says "running scripts is disabled", run `Set-ExecutionPolicy -Scope Process Bypass` in that terminal and try again (it only affects that window).

Options for the launcher (type after the file name, for example `RUN_PROJECT.bat --no-browser`):

| Option | Meaning |
|---|---|
| `--no-browser` | do not open the browser |
| `--no-import` | do not load the bundled communities automatically |
| `--check` | install what is missing, then stop |
| `--reinstall` | delete `.venv` and `node_modules` and install again |
| `--backend-port N`, `--frontend-port N` | choose ports (otherwise the next free ones are used) |
| `--status`, `--stop`, `--doctor` | is it running / stop it / check the computer |

## When something goes wrong

The window stays open and prints the reason in plain words. Everything the launcher did is also written to the `.energiq-run` folder inside the project:

| File | Holds |
|---|---|
| `launcher.log` | every step and message of each run (the previous run is kept as `launcher.log.1`). **Never contains a password.** |
| `backend.log`, `frontend.log` | the output of the two servers |
| `pip-install.log`, `npm-install.log` | package installation |
| `database.log` | the database step |

If you ask someone for help, send them `launcher.log` and the log named in the message. Find your message below.

| What you see | Cause and fix |
|---|---|
| **"Windows protected your PC"** (SmartScreen) or **"Smart App Control blocked part of this app"** | Windows distrusts scripts from a downloaded ZIP. First do step 2.2 (Unblock the ZIP) and extract again. For SmartScreen, "More info" then "Run anyway" is also possible. If it still blocks, do not turn protection off first: open PowerShell in the folder and run `py -3.11 run_energiq.py`. That starts the same launcher through the already-trusted Python. Only if that is also blocked, Smart App Control can be switched off in *Windows Security, App and browser control, Smart App Control settings*. It cannot be turned back on without reinstalling Windows, so treat it as the last resort. The launcher prints a note when it sees Smart App Control switched on. |
| The window flashes and closes | Run it from a Command Prompt instead (`cd` to the folder, type `RUN_PROJECT.bat`) to read the message, or open `.energiq-run\launcher.log`. |
| "Python 3.11, 3.12 or 3.13 was not found" | Install Python from python.org and tick **Add python.exe to PATH**. Close the window and start again. If you have Python 3.14 only, install 3.11 next to it; the `py` launcher finds both. If typing `python` opens the Microsoft Store, install Python from python.org instead. |
| "Node.js was not found" / "too old" | Install the LTS version from nodejs.org, close the window, double-click `RUN_PROJECT.bat` again. |
| "run_energiq.py was not found next to this file" | You started the file from inside the ZIP. Close it, right-click the ZIP, *Extract All*, and run it from the extracted folder. |
| "This folder cannot be used as a working folder" | The folder is on a network location. Copy the whole EnergiQ-AI folder to a local drive such as `C:\EnergiQ`. |
| `pip` or `npm` fails with a network or certificate error | You are offline or behind a proxy. Reconnect and run again; the launcher resumes where it stopped. On a company or college proxy, set `HTTPS_PROXY` in PowerShell first. |
| "The database could not be prepared" | The message says why. Usually the folder is read-only or a sync tool (OneDrive) or antivirus holds the file. Move the project to `C:\EnergiQ`. Details are in `.energiq-run\database.log`. |
| "Port 8000 is already in use" | The launcher picks the next free port by itself. If you forced a port with `--backend-port`, choose another or close the program using it. |
| "Access is denied" or files cannot be deleted | A sync tool (OneDrive) or antivirus is scanning the folder. Move the project to `C:\EnergiQ` and add it to the antivirus exclusions if you can. |
| "The filename or extension is too long" | Windows long-path limit. Extract to a short path such as `C:\EnergiQ`. The launcher prints a note when the path is long. |
| "Did not become ready" or "stopped while starting" | The message shows the last lines of the server's log. A different program may be using the port; run `RUN_PROJECT.bat` again or use `STOP_PROJECT.bat` first. |
| The browser shows "This site can't be reached" | The window printed an error before the "running" box, or you closed it. Read the window, or start again. |
| Sign-in says wrong password | Use the password in the window or in `.energiq-run\admin_login.txt`. If you started an older copy of the project in the same folder, delete `data\energiq.db` and start again. |
| Install broke halfway | `RUN_PROJECT.bat --reinstall` |
| Still stuck | Run `CHECK_ENVIRONMENT.bat` and read the lines marked `MISSING` (must be fixed) or `NOTE` (information). |

## Where to read more

* [`README.md`](README.md): what the project is, results, limits.
* [`FINAL_FEATURE_AUDIT.md`](FINAL_FEATURE_AUDIT.md): every feature, whether it works, and the evidence.
* [`FINAL_TEST_REPORT.md`](FINAL_TEST_REPORT.md): every test run, with the exact command and result, and what could not be tested.
* [`docs/manuals/demo_script.md`](docs/manuals/demo_script.md): a 12-minute demonstration script.
* [`docs/manuals/user_guide.md`](docs/manuals/user_guide.md): the user guide.
