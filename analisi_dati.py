"""Analisi delle statistiche del Padel Tracker da file JSON.

Mostra una tabella riepilogativa e una tabella dei colpi per ciascuno dei quattro
 giocatori. Non richiede librerie esterne.

Avvio: python padel_analisi.py [percorso/file.json]
"""
from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

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
    """Restituisce giocatori, colpi e contatori; supporta export vecchi e nuovi."""
    squadre = dati.get("squadre", {})
    giocatori: list[str] = []
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

    conteggi = {nome: {esito: {colpo: 0 for colpo in colpi} for esito in ESITI} for nome in giocatori}
    if isinstance(aggregate, dict) and aggregate:
        for nome in giocatori:
            for esito, by_colpo in aggregate.get(nome, {}).items():
                if not isinstance(by_colpo, dict):
                    continue
                conteggi.setdefault(nome, {e: {c: 0 for c in colpi} for e in ESITI})
                for colpo, valore in by_colpo.items():
                    if colpo not in colpi:
                        colpi.append(colpo)
                        for n in giocatori:
                            for e in ESITI:
                                conteggi.setdefault(n, {}).setdefault(e, {}).setdefault(colpo, 0)
                    conteggi[nome].setdefault(esito, {}).setdefault(colpo, 0)
                    try:
                        conteggi[nome][esito][colpo] = int(valore or 0)
                    except (ValueError, TypeError):
                        conteggi[nome][esito][colpo] = 0
    else:
        # Fallback se l'export contiene cronologia ma non statistiche aggregate.
        history = dati.get("cronologia_punti", {})
        points = history.get("dati", []) if isinstance(history, dict) else []
        for point in points if isinstance(points, list) else []:
            for action in point.get("azioni_scambio", []):
                nome = action.get("giocatore")
                colpo = action.get("colpo")
                esito = action.get("esito")
                if not nome or not colpo or not esito:
                    continue
                if nome not in conteggi:
                    giocatori.append(nome)
                    conteggi[nome] = {e: {c: 0 for c in colpi} for e in ESITI}
                if colpo not in colpi:
                    colpi.append(colpo)
                    for n in giocatori:
                        for e in ESITI:
                            conteggi[n].setdefault(e, {}).setdefault(colpo, 0)
                conteggi[nome].setdefault(esito, {}).setdefault(colpo, 0)
                conteggi[nome][esito][colpo] += 1

    for nome in giocatori:
        conteggi.setdefault(nome, {})
        for esito in ESITI:
            conteggi[nome].setdefault(esito, {})
            for colpo in colpi:
                conteggi[nome][esito].setdefault(colpo, 0)
    return giocatori, colpi, conteggi


def normalizza_assist(dati: dict, giocatori: list[str]) -> dict[str, int]:
    """Usa il conteggio aggregato; in alternativa conta gli assist in cronologia."""
    raw = dati.get("assist_aggregate")
    if isinstance(raw, dict):
        risultati = {nome: 0 for nome in giocatori}
        for nome in giocatori:
            try:
                risultati[nome] = int(raw.get(nome, 0) or 0)
            except (ValueError, TypeError):
                risultati[nome] = 0
        # L'oggetto esiste solo nelle versioni nuove del tracker: è autorevole.
        return risultati

    risultati = {nome: 0 for nome in giocatori}
    history = dati.get("cronologia_punti", {})
    points = history.get("dati", []) if isinstance(history, dict) else []
    for point in points if isinstance(points, list) else []:
        assistente = point.get("assistente")
        if assistente:
            risultati[assistente] = risultati.get(assistente, 0) + 1
    return risultati


def _punti_cronologia(dati: dict) -> list[dict]:
    history = dati.get("cronologia_punti", {})
    points = history.get("dati", []) if isinstance(history, dict) else []
    return points if isinstance(points, list) else []


def analizza_servizio_risposta(dati: dict, giocatori: list[str]) -> dict:
    """Calcola punti giocati/vinti al servizio e in risposta per singolo giocatore.

    Il ricevitore è quello indicato nel record del punto. Per esportazioni che
    contengono i lati e il lato di battuta ma non il ricevitore, prova a ricavarlo.
    Non attribuisce la risposta individuale nei JSON più vecchi privi di questi dati.
    """
    squadre = dati.get("squadre", {})
    team_by_player: dict[str, str] = {}
    team_members: dict[str, list[str]] = {}
    if isinstance(squadre, dict):
        for team, members in squadre.items():
            if isinstance(members, list):
                team_members[team] = members
                for nome in members:
                    team_by_player[nome] = team

    lati = dati.get("lati_giocatori", {})
    if not isinstance(lati, dict):
        lati = {}

    serve = {nome: {"giocati": 0, "vinti": 0} for nome in giocatori}
    risposta = {nome: {"giocati": 0, "vinti": 0} for nome in giocatori}
    punti_servizio_tracciati = 0
    punti_risposta_tracciati = 0

    for point in _punti_cronologia(dati):
        battitore = point.get("giocatore_al_servizio")
        team_servizio = point.get("squadra_al_servizio") or team_by_player.get(battitore)
        team_punto = point.get("squadra_che_fa_punto")

        if battitore in serve and team_servizio and team_punto:
            serve[battitore]["giocati"] += 1
            punti_servizio_tracciati += 1
            if team_punto == team_servizio:
                serve[battitore]["vinti"] += 1

        ricevitore = point.get("giocatore_in_risposta")
        if not ricevitore:
            lato_servizio = point.get("lato_servizio")
            team_ricezione = point.get("squadra_in_risposta")
            if not team_ricezione and team_servizio:
                team_ricezione = next((team for team in team_members if team != team_servizio), None)
            if lato_servizio in ("Destra", "Sinistra") and team_ricezione:
                possibili = [
                    nome for nome in team_members.get(team_ricezione, [])
                    if lati.get(nome) == lato_servizio
                ]
                if len(possibili) == 1:
                    ricevitore = possibili[0]

        if ricevitore in risposta and team_punto:
            team_ricezione = team_by_player.get(ricevitore) or point.get("squadra_in_risposta")
            if team_ricezione:
                risposta[ricevitore]["giocati"] += 1
                punti_risposta_tracciati += 1
                if team_punto == team_ricezione:
                    risposta[ricevitore]["vinti"] += 1

    return {
        "servizio_disponibile": punti_servizio_tracciati > 0,
        "risposta_disponibile": punti_risposta_tracciati > 0,
        "per_giocatore_servizio": serve,
        "per_giocatore_risposta": risposta,
        "team_by_player": team_by_player,
        "team_members": team_members,
    }


def rapporto(vinti: int, giocati: int) -> str:
    return f"{vinti}/{giocati} ({100 * vinti / giocati:.1f}%)" if giocati else "N/D"


def percentuale(parte: int, totale: int) -> float:
    return 100.0 * parte / totale if totale else 0.0


class PadelAnalysisApp:
    def __init__(self, root: tk.Tk, percorso: str, dati: dict):
        self.root = root
        self.percorso = percorso
        self.dati = dati
        root.title("Analisi statistiche Padel")
        root.geometry("1510x850")
        root.minsize(1080, 700)

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
            parent=self.root,
            title="Scegli il JSON esportato dal Padel Tracker",
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
        self.assist = normalizza_assist(self.dati, self.giocatori)
        self.servizio_risposta = analizza_servizio_risposta(self.dati, self.giocatori)
        self.label_file.configure(text=f"File analizzato: {self.percorso}")
        self.crea_tab_riepilogo()
        self.crea_tab_dettaglio()

    @staticmethod
    def crea_tree(parent, columns, headings, widths):
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True, padx=10, pady=10)
        tree = ttk.Treeview(wrap, columns=columns, show="headings")
        for col, heading, width in zip(columns, headings, widths):
            tree.heading(col, text=heading)
            tree.column(col, width=width, minwidth=65, anchor="center", stretch=True)
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
                "% colpi coppia = colpi registrati dal giocatore / totale colpi dei due compagni. "
                "Servizio e risposta sono mostrati come punti vinti / punti giocati. "
                "La risposta individuale richiede il lato del servizio e il lato assegnato ai giocatori."
            ),
            wraplength=1400,
            justify="left",
            padding=(12, 10, 12, 5),
        ).pack(fill="x")

        columns = ("giocatore", "winner", "assist", "err_nf", "err_tot", "numero_colpi", "pct_coppia", "servizio", "risposta")
        headings = (
            "Giocatore", "Winner", "Assist", "Errori non forzati", "Errori totali",
            "Numero colpi", "% colpi coppia", "Punti vinti al servizio", "Punti vinti in risposta",
        )
        widths = (190, 85, 80, 145, 115, 105, 120, 200, 200)
        tree = self.crea_tree(frame, columns, headings, widths)

        shots = {nome: self.numero_colpi(nome) for nome in self.giocatori}
        squadra_di = self.servizio_risposta["team_by_player"]
        membri_squadra = self.servizio_risposta["team_members"]
        for nome in self.giocatori:
            winner = self.totale(nome, "Winner")
            err_nf = self.totale(nome, "Errore non forzato")
            err_f = self.totale(nome, "Errore forzato")
            team = squadra_di.get(nome)
            totale_coppia = sum(shots.get(compagno, 0) for compagno in membri_squadra.get(team, []))
            quota = f"{percentuale(shots[nome], totale_coppia):.1f}%" if totale_coppia else "N/D"

            serve = self.servizio_risposta["per_giocatore_servizio"].get(nome, {"vinti": 0, "giocati": 0})
            risposta = self.servizio_risposta["per_giocatore_risposta"].get(nome, {"vinti": 0, "giocati": 0})
            serve_text = rapporto(serve["vinti"], serve["giocati"]) if self.servizio_risposta["servizio_disponibile"] else "N/D — dati assenti"
            risposta_text = rapporto(risposta["vinti"], risposta["giocati"]) if self.servizio_risposta["risposta_disponibile"] else "N/D — dati assenti"

            tree.insert("", "end", values=(
                nome,
                winner,
                self.assist.get(nome, 0),
                err_nf,
                err_f + err_nf,
                shots[nome],
                quota,
                serve_text,
                risposta_text,
            ))

        avvisi = []
        if not self.servizio_risposta["servizio_disponibile"]:
            avvisi.append(
                "Servizio non disponibile: il JSON non contiene punti con il battitore registrato. "
                "Esporta la partita con il tracker aggiornato."
            )
        if not self.servizio_risposta["risposta_disponibile"]:
            avvisi.append(
                "Risposta individuale non disponibile: esporta di nuovo il JSON con la versione aggiornata, "
                "impostando i lati Destra/Sinistra prima del primo colpo."
            )
        if avvisi:
            ttk.Label(
                frame, text="\n".join(avvisi), foreground="#8a4b08",
                wraplength=1400, justify="left", padding=(12, 5, 12, 10),
            ).pack(fill="x")

    def crea_tab_dettaglio(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Dettaglio per colpo")
        ttk.Label(
            frame,
            text="Le quattro tabelle seguenti riportano tutti i colpi per ciascun giocatore, anche quelli con zero occorrenze.",
            padding=(12, 10),
        ).pack(fill="x")
        nb = ttk.Notebook(frame)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        for nome in self.giocatori:
            page = ttk.Frame(nb)
            nb.add(page, text=nome)
            tree = self.crea_tree(
                page,
                ("colpo", "winner", "err_f", "err_nf", "err_tot", "totale"),
                ("Colpo", "Winner", "Errore forzato", "Errore non forzato", "Errori totali", "Totale colpi"),
                (240, 100, 145, 160, 130, 125),
            )
            for colpo in self.colpi:
                win = self.conteggi.get(nome, {}).get("Winner", {}).get(colpo, 0)
                ef = self.conteggi.get(nome, {}).get("Errore forzato", {}).get(colpo, 0)
                enf = self.conteggi.get(nome, {}).get("Errore non forzato", {}).get(colpo, 0)
                tree.insert("", "end", values=(
                    colpo, win, ef, enf, ef + enf, self.totale_colpo(nome, colpo)
                ))


def main():
    percorso = sys.argv[1] if len(sys.argv) > 1 else None
    if not percorso:
        dialog = tk.Tk()
        dialog.withdraw()
        percorso = filedialog.askopenfilename(
            parent=dialog,
            title="Scegli il JSON esportato dal Padel Tracker",
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
