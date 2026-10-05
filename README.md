# FIRA — FDMS Input Tax Recovery Platform

FIRA is a reconciliation and exception-management system that compares accounts-payable records against ZIMRA-reported invoices to identify unclaimable VAT and generate supplier correction correspondence.

## Running the Application

### Prerequisites
- Docker & Docker Compose
- Windows: PowerShell (pwsh) or WSL2
- Linux/Mac: `make`

### Launch Development Stack
On Windows (PowerShell):
```powershell
./run.ps1 dev
```

On Linux / WSL2:
```bash
make dev
```

### Running Tests
On Windows (PowerShell):
```powershell
./run.ps1 test
```

On Linux / WSL2:
```bash
make test
```

### Code Formatting & Quality
On Windows (PowerShell):
```powershell
./run.ps1 lint
```

On Linux / WSL2:
```bash
make lint
```
