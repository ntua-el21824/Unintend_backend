# UnIntend Backend (Setup + Βάση)

## Προαπαιτούμενα

- Windows
- Python 3.x (προτείνεται 3.10+)
- Git
- PowerShell (για activation του venv)

## 1) Κατέβασμα κώδικα (git clone)

```powershell
git clone https://github.com/elenippn/Unintend_backend.git
```

Μπες στον φάκελο που κατέβασες το project (βάζεις το **δικό σου** path):

```powershell
cd C:\Users\<TO_ONOMA_SOU>\<KAPOIOS_FAKOLOS>\Unintend_backend
```

## 2) Δημιουργία virtual environment

```powershell
py -m venv .venv
```

## 3) Ενεργοποίηση venv (PowerShell)

```powershell
.venv\Scripts\Activate.ps1
```

Αν σου βγάλει error για execution policy, τρέξε **μία φορά**:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

…και μετά ξανατρέξε:

```powershell
.venv\Scripts\Activate.ps1
```

## 4) Εγκατάσταση dependencies

```powershell
pip install -r requirements.txt
```

## 5) Βάση δεδομένων (SQLite) + Seed

Η βάση είναι **SQLite** και αποθηκεύεται ως αρχείο:

- `unintend.db` (δημιουργείται στο root του project όταν τρέχεις το app/seed)

Για να “κατεβάσεις/στήσεις” τη βάση με αρχικά δεδομένα (μόνο την **πρώτη φορά**):

```powershell
py -m app.seed
```

Το seed τυπώνει και έτοιμους test λογαριασμούς (π.χ. `eleni / pass1234`).

## 6) Εκκίνηση server

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

- http://127.0.0.1:8000/

## 7) (Optional) Reset της βάσης

Αν θέλεις να ξεκινήσεις από την αρχή:

1. Κλείσε τον server
2. Σβήσε το αρχείο `unintend.db`
3. Ξανατρέξε:

```powershell
py -m app.seed
```

## Έτοιμη

Αν όλα τα παραπάνω τρέξουν χωρίς errors, είσαι έτοιμη.
