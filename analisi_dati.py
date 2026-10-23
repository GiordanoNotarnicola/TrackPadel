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

def _indice_squadra(nome_squadra: str | None, nomi_squadre: list[str]) -> int | None:
    """Converte il nome della squadra nell'indice usato dal punteggio (0/1)."""
    if nome_squadra is None:
        return None
    try:
        return nomi_squadre.index(nome_squadra)
    except ValueError:
        return None


def _squadra_ha_game_point(stato: dict, indice_squadra: int) -> bool:
    """Dice se la squadra avrebbe un game point vincendo il punto successivo.

    Esclude i tie-break. Comprende i punteggi 0/15/30-40, AD1/AD2 e lo Star Point.
    """
    if not isinstance(stato, dict):
        return False
    if stato.get("tie_break"):
        return False

    testo = str(stato.get("punti_game", "")).strip().upper()
    if testo.startswith("TB "):
        return False
    if stato.get("star_point") or testo == "STAR POINT":
        return True

    parti = testo.split("-", 1)
    if len(parti) != 2:
        return False
    token = [parte.strip() for parte in parti]
    if indice_squadra not in (0, 1):
        return False

    mio = token[indice_squadra]
    avversario = token[1 - indice_squadra]
    if mio.startswith("AD"):
        return True
    return mio == "40" and avversario in {"0", "15", "30"}


def _game_terminato(record: dict) -> bool:
    """Rileva la chiusura del game confrontando lo stato prima/dopo il punto."""
    prima = record.get("punteggio_prima") or {}
    dopo = record.get("punteggio_dopo") or {}
    if prima.get("game") is not None and dopo.get("game") is not None:
        if str(prima.get("game")) != str(dopo.get("game")):
            return True
    if prima.get("set") is not None and dopo.get("set") is not None:
        if str(prima.get("set")) != str(dopo.get("set")):
            return True
    return bool(record.get("set_completato_in_questa_azione"))


def _ricevitore_record(record: dict, squadra_servizio: str, team_members: dict,
                       lati: dict, team_by_player: dict) -> str | None:
    """Usa il ricevitore salvato nel punto; prova a ricavarlo nei JSON compatibili."""
    ricevitore = record.get("giocatore_in_risposta")
    if ricevitore and ricevitore in team_by_player:
        return ricevitore
    squadra_risposta = record.get("squadra_in_risposta")
    if not squadra_risposta:
        squadra_risposta = next((team for team in team_members if team != squadra_servizio), None)
    lato = record.get("lato_servizio")
    if lato in ("Destra", "Sinistra") and squadra_risposta:
        candidati = [nome for nome in team_members.get(squadra_risposta, []) if lati.get(nome) == lato]
        if len(candidati) == 1:
            return candidati[0]
    return None


def analizza_break_point(dati: dict, giocatori: list[str]) -> dict:
    """Analizza break point, conversioni, salvataggi e modalità dei break subiti.

    Usa esclusivamente la cronologia del JSON esportato. I risultati di squadra
    possono essere calcolati se è registrata la squadra al servizio; i risultati
    individuali richiedono anche battitore e/o ricevitore identificabili.
    """
    raw_squadre = dati.get("squadre", {})
    if isinstance(raw_squadre, dict):
        nomi_squadre = [nome for nome, membri in raw_squadre.items() if isinstance(membri, list)]
    else:
        nomi_squadre = []
    team_members = {nome: raw_squadre.get(nome, []) for nome in nomi_squadre}
    team_by_player = {
        giocatore: squadra
        for squadra, membri in team_members.items()
        for giocatore in membri
    }
    lati = dati.get("lati_giocatori", {})
    if not isinstance(lati, dict):
        lati = {}

    player_stats = {
        nome: {
            "bp_avuti": 0, "bp_convertiti": 0, "bp_persi": 0,
            "bp_affrontati": 0, "bp_salvati": 0,
            "break_fatti": 0, "break_subiti": 0,
            "winner_break": 0,
            "errori_forzati_break": 0, "errori_non_forzati_break": 0,
        }
        for nome in giocatori
    }
    team_stats = {
        nome: {
            "bp_avuti": 0, "bp_convertiti": 0, "bp_persi": 0,
            "bp_affrontati": 0, "bp_salvati": 0,
            "break_fatti": 0, "break_subiti": 0,
        }
        for nome in nomi_squadre
    }

    break_points = []
    break_subiti = []
    bp_senza_ricevitore = 0
    bp_senza_battitore = 0
    bp_vinti_senza_game_chiuso = 0

    for record in _punti_cronologia(dati):
        prima = record.get("punteggio_prima") or {}
        if not prima:
            continue

        battitore = record.get("giocatore_al_servizio")
        squadra_servizio = record.get("squadra_al_servizio") or team_by_player.get(battitore)
        idx_servizio = _indice_squadra(squadra_servizio, nomi_squadre)
        if idx_servizio is None or len(nomi_squadre) != 2:
            continue
        idx_risposta = 1 - idx_servizio
        squadra_risposta = nomi_squadre[idx_risposta]
        if not _squadra_ha_game_point(prima, idx_risposta):
            continue

        # Un break point è una chance della squadra in risposta di chiudere il game.
        ricevitore = _ricevitore_record(record, squadra_servizio, team_members, lati, team_by_player)
        squadra_punto = record.get("squadra_che_fa_punto")
        giocatore_finale = record.get("giocatore")
        esito = record.get("esito", "N/D")
        colpo = record.get("colpo", "N/D")
        if not squadra_punto and giocatore_finale in team_by_player:
            squadra_finale = team_by_player[giocatore_finale]
            if esito == "Winner":
                squadra_punto = squadra_finale
            elif esito in ("Errore forzato", "Errore non forzato"):
                squadra_punto = next((team for team in nomi_squadre if team != squadra_finale), None)

        indice_punto = _indice_squadra(squadra_punto, nomi_squadre)
        chiuso_game = _game_terminato(record)
        punto_risposta_vinto = indice_punto == idx_risposta
        punto_servizio_vinto = indice_punto == idx_servizio
        convertito = punto_risposta_vinto and chiuso_game
        salvato = punto_servizio_vinto
        if punto_risposta_vinto and not chiuso_game:
            bp_vinti_senza_game_chiuso += 1

        if squadra_risposta in team_stats:
            team_stats[squadra_risposta]["bp_avuti"] += 1
        if squadra_servizio in team_stats:
            team_stats[squadra_servizio]["bp_affrontati"] += 1
        if ricevitore in player_stats:
            player_stats[ricevitore]["bp_avuti"] += 1
        else:
            bp_senza_ricevitore += 1
        if battitore in player_stats:
            player_stats[battitore]["bp_affrontati"] += 1
        else:
            bp_senza_battitore += 1

        if convertito:
            team_stats[squadra_risposta]["bp_convertiti"] += 1
            team_stats[squadra_risposta]["break_fatti"] += 1
            team_stats[squadra_servizio]["break_subiti"] += 1
            if ricevitore in player_stats:
                player_stats[ricevitore]["bp_convertiti"] += 1
                player_stats[ricevitore]["break_fatti"] += 1
            if battitore in player_stats:
                player_stats[battitore]["break_subiti"] += 1
        elif salvato:
            team_stats[squadra_risposta]["bp_persi"] += 1
            team_stats[squadra_servizio]["bp_salvati"] += 1
            if ricevitore in player_stats:
                player_stats[ricevitore]["bp_persi"] += 1
            if battitore in player_stats:
                player_stats[battitore]["bp_salvati"] += 1

        if convertito:
            if esito == "Winner" and team_by_player.get(giocatore_finale) == squadra_risposta:
                if giocatore_finale in player_stats:
                    player_stats[giocatore_finale]["winner_break"] += 1
                causa = f"Winner della squadra in risposta ({colpo})"
                tipo_chiusura = "Winner"
                autore_errore = "—"
            elif esito in ("Errore forzato", "Errore non forzato") and team_by_player.get(giocatore_finale) == squadra_servizio:
                causa = f"{esito} di {giocatore_finale} ({colpo})"
                tipo_chiusura = esito
                autore_errore = giocatore_finale
                chiave = "errori_forzati_break" if esito == "Errore forzato" else "errori_non_forzati_break"
                if giocatore_finale in player_stats:
                    player_stats[giocatore_finale][chiave] += 1
            else:
                causa = f"{esito} — {giocatore_finale or 'giocatore non identificato'} ({colpo})"
                tipo_chiusura = esito
                autore_errore = "—"

            detail = {
                "punto_numero": record.get("punto_numero", "?"),
                "set": prima.get("set", "N/D"),
                "game_prima": prima.get("game", "N/D"),
                "punteggio_prima": prima.get("punti_game", "N/D"),
                "giocatore_al_servizio": battitore or "N/D",
                "squadra_al_servizio": squadra_servizio,
                "giocatore_in_risposta": ricevitore or "N/D",
                "squadra_in_risposta": squadra_risposta,
                "giocatore_finale": giocatore_finale or "N/D",
                "colpo_finale": colpo,
                "esito_finale": esito,
                "tipo_chiusura": tipo_chiusura,
                "causa_break": causa,
                "autore_errore": autore_errore,
                "break_subito_da": battitore or squadra_servizio,
                "break_fatto_da": ricevitore or squadra_risposta,
            }
            break_subiti.append(detail)

        if convertito:
            stato_bp = "CONVERTITO — break fatto"
        elif salvato:
            stato_bp = "SALVATO dal servizio"
        elif punto_risposta_vinto:
            stato_bp = "Punto BP vinto, ma game non risulta chiuso"
        else:
            stato_bp = "Esito non attribuibile dal JSON"

        break_points.append({
            "punto_numero": record.get("punto_numero", "?"),
            "set": prima.get("set", "N/D"),
            "game_prima": prima.get("game", "N/D"),
            "punteggio_prima": prima.get("punti_game", "N/D"),
            "giocatore_al_servizio": battitore or "N/D",
            "squadra_al_servizio": squadra_servizio,
            "giocatore_in_risposta": ricevitore or "N/D",
            "squadra_in_risposta": squadra_risposta,
            "giocatore_finale": giocatore_finale or "N/D",
            "colpo_finale": colpo,
            "esito_finale": esito,
            "squadra_che_fa_punto": squadra_punto or "N/D",
            "stato_bp": stato_bp,
            "convertito": convertito,
            "salvato": salvato,
        })

    return {
        "per_giocatore": player_stats,
        "per_squadra": team_stats,
        "break_points": break_points,
        "break_subiti": break_subiti,
        "numero_break_point": len(break_points),
        "numero_break_subiti": len(break_subiti),
        "bp_senza_ricevitore": bp_senza_ricevitore,
        "bp_senza_battitore": bp_senza_battitore,
        "bp_vinti_senza_game_chiuso": bp_vinti_senza_game_chiuso,
        "squadre": nomi_squadre,
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
        self.break_analysis = analizza_break_point(self.dati, self.giocatori)
        self.label_file.configure(text=f"File analizzato: {self.percorso}")
        self.crea_tab_riepilogo()
        self.crea_tab_dettaglio()
        self.crea_tab_break_point()

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


    def crea_tab_break_point(self):
        """Mostra riepilogo di squadra/giocatore e dettaglio dei break point."""
        analisi = self.break_analysis
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Break point")

        summary = (
            f"Break point individuati: {analisi['numero_break_point']}  |  "
            f"Break fatti: {analisi['numero_break_subiti']}"
        )
        ttk.Label(frame, text=summary, font=("TkDefaultFont", 11, "bold"),
                  padding=(12, 10, 12, 4)).pack(fill="x")
        ttk.Label(
            frame,
            text=(
                "Un break point viene contato quando la squadra in risposta può vincere il game con il punto successivo. "
                "'Convertito' significa che la risposta vince il punto e il game; 'salvato' significa che la squadra al "
                "servizio vince il punto. I tie-break sono esclusi. I break subiti sono classificati in base all'azione "
                "che ha chiuso il game: winner avversario, errore forzato o errore non forzato."
            ),
            wraplength=1400, justify="left", padding=(12, 0, 12, 8),
        ).pack(fill="x")

        nb = ttk.Notebook(frame)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Tabella giocatori: attribuzione individuale basata sul battitore e sul ricevitore registrati.
        page_player = ttk.Frame(nb)
        nb.add(page_player, text="Riepilogo giocatori")
        ttk.Label(
            page_player,
            text=(
                "Le statistiche individuali dipendono dal battitore/ricevitore identificato nel JSON. "
                "Le statistiche di squadra, invece, restano valide quando è nota la squadra al servizio."
            ),
            wraplength=1350, justify="left", padding=(10, 8),
        ).pack(fill="x")
        cols = (
            "giocatore", "bp_avuti", "convertiti", "persi", "pct_conv",
            "bp_affrontati", "salvati", "pct_salv", "break_fatti", "break_subiti",
            "winner_break", "ef_break", "enf_break",
        )
        heads = (
            "Giocatore", "BP avuti in risposta", "Convertiti", "Persi", "% conversione",
            "BP affrontati al servizio", "Salvati", "% salvataggio", "Break fatti", "Break subiti",
            "Winner su BP", "Errori forzati che causano break", "Errori non forzati che causano break",
        )
        widths = (175, 125, 85, 75, 105, 150, 75, 105, 90, 100, 95, 175, 195)
        tree_player = self.crea_tree(page_player, cols, heads, widths)
        for nome in self.giocatori:
            st = analisi["per_giocatore"].get(nome, {})
            conv = st.get("bp_convertiti", 0)
            avuti = st.get("bp_avuti", 0)
            salvati = st.get("bp_salvati", 0)
            affrontati = st.get("bp_affrontati", 0)
            tree_player.insert("", "end", values=(
                nome,
                avuti,
                conv,
                st.get("bp_persi", 0),
                f"{100 * conv / avuti:.1f}%" if avuti else "N/D",
                affrontati,
                salvati,
                f"{100 * salvati / affrontati:.1f}%" if affrontati else "N/D",
                st.get("break_fatti", 0),
                st.get("break_subiti", 0),
                st.get("winner_break", 0),
                st.get("errori_forzati_break", 0),
                st.get("errori_non_forzati_break", 0),
            ))

        # Tabella aggregata per squadra, utile anche quando non si può individuare il ricevitore individuale.
        page_team = ttk.Frame(nb)
        nb.add(page_team, text="Riepilogo squadre")
        ttk.Label(
            page_team,
            text="Statistiche di squadra conteggiate dalla cronologia dei punti con il servizio identificabile.",
            padding=(10, 8),
        ).pack(fill="x")
        team_cols = (
            "squadra", "bp_avuti", "convertiti", "persi", "pct_conv",
            "bp_affrontati", "salvati", "pct_salv", "break_fatti", "break_subiti",
        )
        team_heads = (
            "Squadra", "BP avuti in risposta", "Convertiti", "Persi", "% conversione",
            "BP affrontati al servizio", "Salvati", "% salvataggio", "Break fatti", "Break subiti",
        )
        team_tree = self.crea_tree(page_team, team_cols, team_heads,
                                   (160, 130, 95, 80, 110, 160, 80, 115, 100, 105))
        for team in analisi["squadre"]:
            st = analisi["per_squadra"].get(team, {})
            avuti = st.get("bp_avuti", 0)
            conv = st.get("bp_convertiti", 0)
            affrontati = st.get("bp_affrontati", 0)
            salvati = st.get("bp_salvati", 0)
            team_tree.insert("", "end", values=(
                team, avuti, conv, st.get("bp_persi", 0),
                f"{100 * conv / avuti:.1f}%" if avuti else "N/D",
                affrontati, salvati,
                f"{100 * salvati / affrontati:.1f}%" if affrontati else "N/D",
                st.get("break_fatti", 0), st.get("break_subiti", 0),
            ))

        # Cronologia di tutte le occasioni break: salvate e convertite.
        page_all = ttk.Frame(nb)
        nb.add(page_all, text="Tutti i break point")
        ttk.Label(
            page_all,
            text="Una riga per ogni break point affrontato: vedi punteggio prima del punto, esito, colpo finale e se è stato convertito o salvato.",
            wraplength=1350, justify="left", padding=(10, 8),
        ).pack(fill="x")
        all_cols = (
            "punto", "set", "game", "punteggio", "battitore", "squadra_servizio",
            "ricevitore", "giocatore_finale", "colpo", "esito", "punto_a", "stato",
        )
        all_heads = (
            "Punto #", "Set", "Game prima", "Punteggio", "Battitore", "Squadra al servizio",
            "Ricevitore", "Ultimo giocatore", "Colpo finale", "Esito finale", "Punto a", "Risultato BP",
        )
        all_widths = (70, 70, 100, 100, 150, 135, 145, 155, 130, 135, 120, 230)
        tree_all = self.crea_tree(page_all, all_cols, all_heads, all_widths)
        for r in analisi["break_points"]:
            tree_all.insert("", "end", values=(
                r["punto_numero"], r["set"], r["game_prima"], r["punteggio_prima"],
                r["giocatore_al_servizio"], r["squadra_al_servizio"], r["giocatore_in_risposta"],
                r["giocatore_finale"], r["colpo_finale"], r["esito_finale"],
                r["squadra_che_fa_punto"], r["stato_bp"],
            ))

        # Solo i break effettivamente convertiti, classificati per tipo di chiusura.
        page_broken = ttk.Frame(nb)
        nb.add(page_broken, text="Break subiti e causa")
        ttk.Label(
            page_broken,
            text=(
                "Questa tabella contiene soltanto i punti in cui il break point è stato convertito e il game risulta chiuso. "
                "La causa indica il winner o l'errore decisivo; il dettaglio dell'autore dell'errore è separato dal battitore."
            ),
            wraplength=1350, justify="left", padding=(10, 8),
        ).pack(fill="x")
        broken_cols = (
            "punto", "set", "game", "punteggio", "battitore", "squadra_servizio",
            "ricevitore", "autore", "colpo", "esito", "causa", "break_subito", "break_fatto",
        )
        broken_heads = (
            "Punto #", "Set", "Game prima", "Punteggio BP", "Battitore", "Squadra che serve",
            "Ricevitore", "Autore azione finale", "Colpo finale", "Esito", "Causa del break",
            "Break subito da", "Break fatto da",
        )
        broken_widths = (70, 70, 100, 105, 145, 130, 145, 155, 125, 130, 250, 145, 145)
        tree_broken = self.crea_tree(page_broken, broken_cols, broken_heads, broken_widths)
        for r in analisi["break_subiti"]:
            tree_broken.insert("", "end", values=(
                r["punto_numero"], r["set"], r["game_prima"], r["punteggio_prima"],
                r["giocatore_al_servizio"], r["squadra_al_servizio"], r["giocatore_in_risposta"],
                r["giocatore_finale"], r["colpo_finale"], r["esito_finale"], r["causa_break"],
                r["break_subito_da"], r["break_fatto_da"],
            ))

        avvisi = []
        if analisi["numero_break_point"] == 0:
            avvisi.append(
                "Nessun break point riconosciuto. Verifica che il JSON contenga la cronologia con punteggio_prima, "
                "squadra_al_servizio e punteggio_dopo. I vecchi export senza questi campi non permettono questa analisi."
            )
        if analisi["bp_senza_ricevitore"]:
            avvisi.append(
                f"{analisi['bp_senza_ricevitore']} break point non attribuibili individualmente al ricevitore: "
                "il riepilogo di squadra li include comunque."
            )
        if analisi["bp_senza_battitore"]:
            avvisi.append(
                f"{analisi['bp_senza_battitore']} break point senza battitore identificabile: "
                "non sono attribuiti al riepilogo individuale del servizio."
            )
        if analisi["bp_vinti_senza_game_chiuso"]:
            avvisi.append(
                f"Attenzione: in {analisi['bp_vinti_senza_game_chiuso']} casi la squadra in risposta ha vinto un punto BP, "
                "ma nel JSON non risulta la chiusura del game. Questi casi non sono conteggiati come break convertiti."
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
