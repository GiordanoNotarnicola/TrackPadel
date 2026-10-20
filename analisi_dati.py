"""Dashboard di analisi del Padel Tracker: tabelle e grafici dal JSON esportato.

Avvio: python padel_analisi.py [percorso/file.json]
Dipendenze: python -m pip install matplotlib
"""
from __future__ import annotations
import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except ImportError as exc:
    raise SystemExit("Per i grafici installa matplotlib: python -m pip install matplotlib") from exc

COLPI_DEFAULT = [
    "Vibora", "Smash", "Bandeja", "Rullo", "Volee dritto", "Volee rovescio",
    "Bajada", "Blocco", "Pallonetto", "Difesa dritto", "Difesa rovescio",
]
ESITI = ["Winner", "Errore forzato", "Errore non forzato", "In gioco"]


def carica_json(percorso: str | Path) -> dict:
    with open(percorso, "r", encoding="utf-8") as file:
        dati = json.load(file)
    if not isinstance(dati, dict):
        raise ValueError("Il file JSON non contiene un oggetto valido.")
    if "statistiche_aggregate" not in dati and "cronologia_punti" not in dati:
        raise ValueError("Il file non sembra un export del Padel Tracker.")
    return dati


def normalizza_statistiche(dati: dict):
    """Restituisce giocatori, colpi e contatori; compatibile anche con vecchi JSON."""
    squadre = dati.get("squadre", {})
    giocatori = []
    if isinstance(squadre, dict):
        for nomi in squadre.values():
            if isinstance(nomi, list):
                for nome in nomi:
                    if nome not in giocatori:
                        giocatori.append(nome)
    aggregate = dati.get("statistiche_aggregate", {})
    if not giocatori and isinstance(aggregate, dict):
        giocatori = list(aggregate.keys())

    colpi = list(COLPI_DEFAULT)
    if isinstance(aggregate, dict):
        for stati in aggregate.values():
            if isinstance(stati, dict):
                for by_colpo in stati.values():
                    if isinstance(by_colpo, dict):
                        for colpo in by_colpo:
                            if colpo not in colpi:
                                colpi.append(colpo)

    conteggi = {n: {e: {c: 0 for c in colpi} for e in ESITI} for n in giocatori}
    if isinstance(aggregate, dict) and aggregate:
        for nome in giocatori:
            for esito, by_colpo in aggregate.get(nome, {}).items():
                if not isinstance(by_colpo, dict):
                    continue
                for colpo, valore in by_colpo.items():
                    if colpo not in colpi:
                        colpi.append(colpo)
                        for n in giocatori:
                            for e in ESITI:
                                conteggi[n][e].setdefault(colpo, 0)
                    conteggi[nome].setdefault(esito, {}).setdefault(colpo, 0)
                    try:
                        conteggi[nome][esito][colpo] = int(valore or 0)
                    except (ValueError, TypeError):
                        conteggi[nome][esito][colpo] = 0
    else:
        # Fallback per eventuali export che contengano la cronologia ma non i totali.
        history = dati.get("cronologia_punti", {})
        points = history.get("dati", []) if isinstance(history, dict) else []
        for point in points if isinstance(points, list) else []:
            for action in point.get("azioni_scambio", []):
                nome, colpo, esito = action.get("giocatore"), action.get("colpo"), action.get("esito")
                if not nome or not colpo or not esito:
                    continue
                if nome not in conteggi:
                    giocatori.append(nome)
                    conteggi[nome] = {e: {c: 0 for c in colpi} for e in ESITI}
                if colpo not in colpi:
                    colpi.append(colpo)
                    for n in giocatori:
                        for e in ESITI:
                            conteggi[n][e].setdefault(colpo, 0)
                conteggi[nome].setdefault(esito, {}).setdefault(colpo, 0)
                conteggi[nome][esito][colpo] += 1

    for nome in giocatori:
        conteggi.setdefault(nome, {})
        for esito in ESITI:
            conteggi[nome].setdefault(esito, {})
            for colpo in colpi:
                conteggi[nome][esito].setdefault(colpo, 0)
    return giocatori, colpi, conteggi


def analizza_servizio(dati: dict, giocatori: list[str]) -> dict:
    """Servizio per battitore; risposta aggregata per squadra (il ricevitore non è registrato)."""
    squadre = dati.get("squadre", {})
    giocatore_squadra = {}
    nomi_squadre = list(squadre.keys()) if isinstance(squadre, dict) else []
    if isinstance(squadre, dict):
        for squadra, nomi in squadre.items():
            if isinstance(nomi, list):
                for nome in nomi:
                    giocatore_squadra[nome] = squadra
    history = dati.get("cronologia_punti", {})
    points = history.get("dati", []) if isinstance(history, dict) else []
    serve = {n: {"giocati": 0, "vinti": 0} for n in giocatori}
    return_by_team = {n: {"giocati": 0, "vinti": 0} for n in nomi_squadre}
    tracked = 0
    for point in points if isinstance(points, list) else []:
        battitore = point.get("giocatore_al_servizio")
        squadra_servizio = point.get("squadra_al_servizio") or giocatore_squadra.get(battitore)
        squadra_punto = point.get("squadra_che_fa_punto")
        if not battitore or not squadra_servizio or not squadra_punto:
            continue
        tracked += 1
        serve.setdefault(battitore, {"giocati": 0, "vinti": 0})
        serve[battitore]["giocati"] += 1
        if squadra_punto == squadra_servizio:
            serve[battitore]["vinti"] += 1
        squadra_risposta = next((s for s in nomi_squadre if s != squadra_servizio), None)
        if squadra_risposta:
            return_by_team[squadra_risposta]["giocati"] += 1
            if squadra_punto == squadra_risposta:
                return_by_team[squadra_risposta]["vinti"] += 1
    return {
        "disponibile": tracked > 0,
        "punti_tracciati": tracked,
        "per_giocatore": serve,
        "per_squadra_risposta": return_by_team,
        "giocatore_squadra": giocatore_squadra,
        "nomi_squadre": nomi_squadre,
    }


def rapporto(vinti: int, giocati: int) -> str:
    return f"{vinti}/{giocati} ({100*vinti/giocati:.1f}%)" if giocati else "0/0 (N/D)"


def pct(n: int, d: int) -> float:
    return 100 * n / d if d else 0.0


class PadelAnalysisApp:
    def __init__(self, root: tk.Tk, percorso: str, dati: dict):
        self.root, self.percorso, self.dati = root, percorso, dati
        root.title("Analisi statistiche Padel")
        root.geometry("1400x850")
        root.minsize(1050, 680)
        header = ttk.Frame(root, padding=(12, 10, 12, 5))
        header.pack(fill="x")
        ttk.Label(header, text="ANALISI STATISTICHE PADEL", font=("TkDefaultFont", 17, "bold")).pack(side="left")
        ttk.Button(header, text="Apri un altro JSON", command=self.apri_json).pack(side="right")
        self.label_file = ttk.Label(root, text="", padding=(14, 0, 14, 6))
        self.label_file.pack(fill="x")
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.aggiorna_interfaccia()

    def apri_json(self):
        percorso = filedialog.askopenfilename(
            parent=self.root, title="Scegli il JSON esportato dal Padel Tracker",
            filetypes=[("File JSON", "*.json"), ("Tutti i file", "*.*")],
        )
        if not percorso:
            return
        try:
            dati = carica_json(percorso)
        except (OSError, json.JSONDecodeError, ValueError) as err:
            messagebox.showerror("Impossibile aprire il JSON", str(err), parent=self.root)
            return
        self.percorso, self.dati = percorso, dati
        self.aggiorna_interfaccia()

    def aggiorna_interfaccia(self):
        for tab in self.notebook.tabs():
            self.notebook.forget(tab)
        self.giocatori, self.colpi, self.conteggi = normalizza_statistiche(self.dati)
        self.servizio = analizza_servizio(self.dati, self.giocatori)
        self.label_file.configure(text=f"File analizzato: {self.percorso}")
        self.crea_tab_riepilogo()
        self.crea_tab_dettaglio()
        self.crea_tab_grafici()

    @staticmethod
    def crea_tree(parent, columns, headings, widths):
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True, padx=10, pady=10)
        tree = ttk.Treeview(wrap, columns=columns, show="headings")
        for col, heading, width in zip(columns, headings, widths):
            tree.heading(col, text=heading)
            tree.column(col, width=width, minwidth=65, anchor="center")
        sy = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        sx = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        return tree

    def totale(self, nome: str, esito: str) -> int:
        return sum(self.conteggi.get(nome, {}).get(esito, {}).values())

    def totale_colpo(self, nome: str, colpo: str) -> int:
        return sum(self.conteggi.get(nome, {}).get(esito, {}).get(colpo, 0) for esito in ESITI)

    def numero_colpi(self, nome: str) -> int:
        return sum(self.totale(nome, esito) for esito in ESITI)

    def crea_tab_riepilogo(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Riepilogo giocatori")
        ttk.Label(
            frame,
            text=(
                "Quota colpi = colpi registrati dal giocatore / colpi totali registrati. "
                "Errori totali = errori forzati + non forzati. Punti in risposta è una metrica di squadra, "
                "ripetuta sui due compagni perché il battitore è l'unico giocatore di servizio registrato."
            ),
            wraplength=1300, justify="left",
        ).pack(fill="x", padx=12, pady=(10, 0))
        columns = ("giocatore", "winner", "err_nf", "err_f", "err_tot", "smash", "colpi", "quota", "servizio", "risposta")
        headings = (
            "Giocatore", "Winner", "Errori non forzati", "Errori forzati", "Errori totali",
            "Smash winner/totale", "Numero colpi", "Quota colpi (%)",
            "Punti vinti in servizio", "Punti in risposta (squadra)",
        )
        widths = (190, 80, 140, 115, 105, 145, 105, 105, 180, 210)
        tree = self.crea_tree(frame, columns, headings, widths)
        shot_totals = {n: self.numero_colpi(n) for n in self.giocatori}
        all_shots = sum(shot_totals.values())
        for nome in self.giocatori:
            winner = self.totale(nome, "Winner")
            err_nf = self.totale(nome, "Errore non forzato")
            err_f = self.totale(nome, "Errore forzato")
            smash_total = self.totale_colpo(nome, "Smash")
            smash_winners = self.conteggi.get(nome, {}).get("Winner", {}).get("Smash", 0)
            if self.servizio["disponibile"]:
                svc = self.servizio["per_giocatore"].get(nome, {"vinti": 0, "giocati": 0})
                serve_text = rapporto(svc["vinti"], svc["giocati"])
                team = self.servizio["giocatore_squadra"].get(nome)
                ret = self.servizio["per_squadra_risposta"].get(team, {"vinti": 0, "giocati": 0})
                return_text = rapporto(ret["vinti"], ret["giocati"])
            else:
                serve_text = "N/D — riesporta JSON"
                return_text = "N/D — riesporta JSON"
            tree.insert("", "end", values=(
                nome, winner, err_nf, err_f, err_nf + err_f,
                f"{smash_winners}/{smash_total}", shot_totals[nome],
                f"{pct(shot_totals[nome], all_shots):.1f}%", serve_text, return_text,
            ))
        if not self.servizio["disponibile"]:
            ttk.Label(
                frame,
                text=(
                    "Il JSON non contiene il battitore per ogni punto: servizio e risposta non sono calcolabili. "
                    "Usa il padel_stats.py aggiornato, imposta il giocatore al servizio all'inizio di ogni game "
                    "ed esporta nuovamente il JSON."
                ),
                foreground="#8a4b08", wraplength=1300, justify="left",
            ).pack(fill="x", padx=14, pady=(0, 10))

    def crea_tab_dettaglio(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Winner ed errori per colpo")
        ttk.Label(
            frame,
            text="Ogni scheda riporta tutti i colpi disponibili per un giocatore, inclusi quelli con zero occorrenze.",
            padding=(12, 10),
        ).pack(fill="x")
        nb = ttk.Notebook(frame)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        for nome in self.giocatori:
            page = ttk.Frame(nb)
            nb.add(page, text=nome)
            tree = self.crea_tree(
                page, ("colpo", "winner", "err_f", "err_nf", "err_tot", "totale"),
                ("Colpo", "Winner", "Errore forzato", "Errore non forzato", "Errori totali", "Totale colpi"),
                (240, 100, 140, 160, 130, 120),
            )
            for colpo in self.colpi:
                win = self.conteggi.get(nome, {}).get("Winner", {}).get(colpo, 0)
                ef = self.conteggi.get(nome, {}).get("Errore forzato", {}).get(colpo, 0)
                enf = self.conteggi.get(nome, {}).get("Errore non forzato", {}).get(colpo, 0)
                tree.insert("", "end", values=(colpo, win, ef, enf, ef + enf, self.totale_colpo(nome, colpo)))

    def crea_tab_grafici(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Grafici")
        nb = ttk.Notebook(frame)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        # 1. Winner ed errori per giocatore.
        page = ttk.Frame(nb)
        nb.add(page, text="Winner ed errori")
        fig = Figure(figsize=(10.8, 6.0), dpi=100)
        ax = fig.add_subplot(111)
        x = list(range(len(self.giocatori)))
        width = 0.24
        winners = [self.totale(n, "Winner") for n in self.giocatori]
        forced = [self.totale(n, "Errore forzato") for n in self.giocatori]
        unforced = [self.totale(n, "Errore non forzato") for n in self.giocatori]
        ax.bar([i - width for i in x], winners, width, label="Winner")
        ax.bar(x, forced, width, label="Errore forzato")
        ax.bar([i + width for i in x], unforced, width, label="Errore non forzato")
        ax.set_title("Winner ed errori per giocatore")
        ax.set_ylabel("Numero di colpi")
        ax.set_xticks(x, self.giocatori, rotation=12, ha="right")
        ax.legend()
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        self.aggiungi_figura(page, fig)

        # 2. Smash winner rispetto a tutti gli smash registrati.
        page = ttk.Frame(nb)
        nb.add(page, text="Smash")
        fig = Figure(figsize=(10.8, 6.0), dpi=100)
        ax = fig.add_subplot(111)
        smash_win = [self.conteggi.get(n, {}).get("Winner", {}).get("Smash", 0) for n in self.giocatori]
        smash_altro = [max(0, self.totale_colpo(n, "Smash") - self.conteggi.get(n, {}).get("Winner", {}).get("Smash", 0)) for n in self.giocatori]
        x = list(range(len(self.giocatori)))
        ax.bar(x, smash_win, label="Smash winner")
        ax.bar(x, smash_altro, bottom=smash_win, label="Altri smash registrati")
        ax.set_title("Smash winner e totale smash registrati")
        ax.set_ylabel("Numero di smash")
        ax.set_xticks(x, self.giocatori, rotation=12, ha="right")
        ax.legend()
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        self.aggiungi_figura(page, fig)

        # 3. Winner ed errori aggregati per tipologia di colpo.
        page = ttk.Frame(nb)
        nb.add(page, text="Per tipologia di colpo")
        fig = Figure(figsize=(11.2, 6.2), dpi=100)
        ax = fig.add_subplot(111)
        agg_win = [sum(self.conteggi.get(n, {}).get("Winner", {}).get(c, 0) for n in self.giocatori) for c in self.colpi]
        agg_err = [sum(
            self.conteggi.get(n, {}).get("Errore forzato", {}).get(c, 0)
            + self.conteggi.get(n, {}).get("Errore non forzato", {}).get(c, 0)
            for n in self.giocatori
        ) for c in self.colpi]
        x = list(range(len(self.colpi)))
        width = 0.38
        ax.bar([i - width / 2 for i in x], agg_win, width, label="Winner")
        ax.bar([i + width / 2 for i in x], agg_err, width, label="Errori totali")
        ax.set_title("Winner ed errori per tipologia di colpo — tutti i giocatori")
        ax.set_ylabel("Numero di colpi")
        ax.set_xticks(x, self.colpi, rotation=35, ha="right")
        ax.legend()
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        self.aggiungi_figura(page, fig)

        # 4. Percentuali di servizio e risposta, solo quando sono nel JSON.
        page = ttk.Frame(nb)
        nb.add(page, text="Servizio e risposta")
        if not self.servizio["disponibile"]:
            ttk.Label(
                page,
                text=(
                    "Il JSON non include il battitore di ogni punto.\n\n"
                    "Apri il tracker aggiornato, seleziona il giocatore che serve all'inizio di ogni game "
                    "ed esporta nuovamente le statistiche."
                ), justify="center", anchor="center", font=("TkDefaultFont", 12),
            ).pack(fill="both", expand=True, padx=20, pady=20)
        else:
            fig = Figure(figsize=(10.8, 6.0), dpi=100)
            ax = fig.add_subplot(111)
            serve_pct, return_pct = [], []
            for nome in self.giocatori:
                s = self.servizio["per_giocatore"].get(nome, {"vinti": 0, "giocati": 0})
                serve_pct.append(pct(s["vinti"], s["giocati"]))
                squadra = self.servizio["giocatore_squadra"].get(nome)
                r = self.servizio["per_squadra_risposta"].get(squadra, {"vinti": 0, "giocati": 0})
                return_pct.append(pct(r["vinti"], r["giocati"]))
            x = list(range(len(self.giocatori)))
            width = 0.36
            ax.bar([i - width / 2 for i in x], serve_pct, width, label="Punti vinti quando serve il giocatore")
            ax.bar([i + width / 2 for i in x], return_pct, width, label="Punti vinti in risposta (squadra)")
            ax.set_ylim(0, 100)
            ax.set_ylabel("Punti vinti (%)")
            ax.set_title("Percentuale di punti vinti in servizio e in risposta")
            ax.set_xticks(x, self.giocatori, rotation=12, ha="right")
            ax.legend()
            ax.grid(axis="y", alpha=0.25)
            fig.tight_layout()
            self.aggiungi_figura(page, fig)

    @staticmethod
    def aggiungi_figura(parent, fig):
        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)


def main():
    percorso = sys.argv[1] if len(sys.argv) > 1 else None
    if not percorso:
        dialog = tk.Tk()
        dialog.withdraw()
        percorso = filedialog.askopenfilename(
            parent=dialog, title="Scegli il JSON esportato dal Padel Tracker",
            filetypes=[("File JSON", "*.json"), ("Tutti i file", "*.*")],
        )
        dialog.destroy()
        if not percorso:
            return
    try:
        dati = carica_json(percorso)
    except (OSError, json.JSONDecodeError, ValueError) as err:
        print(f"Errore durante la lettura del JSON: {err}", file=sys.stderr)
        try:
            err_root = tk.Tk()
            err_root.withdraw()
            messagebox.showerror("Impossibile aprire il JSON", str(err), parent=err_root)
            err_root.destroy()
        except tk.TclError:
            pass
        return
    root = tk.Tk()
    PadelAnalysisApp(root, percorso, dati)
    root.mainloop()


if __name__ == "__main__":
    main()
