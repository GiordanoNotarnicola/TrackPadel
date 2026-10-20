"""Padel Tracker: statistiche dei colpi, cronologia dei punti e punteggio live.

Flusso di registrazione:
1. Seleziona il giocatore.
2. Seleziona il colpo.
3. Se lo scambio continua, premi "Continua scambio" (nessun punto assegnato).
4. Se il colpo chiude il punto, seleziona Winner/Errore e premi "Chiudi punto".

Avvio: python padel_stats.py
"""

import copy
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Configurazione partita: modifica i nomi e la lista dei colpi qui.
SQUADRA_1 = ["Giulio Graziotti", "Iacovino"]
SQUADRA_2 = ["Giocatore 3", "Giocatore 4"]
NOMI_SQUADRE = ["Casa", "Fuori"]
LATI_GIOCO = ["Destra", "Sinistra"]
# Assegnazione iniziale modificabile anche dall'interfaccia prima del primo punto.
# Ogni coppia deve avere un giocatore a Destra e uno a Sinistra.
LATI_GIOCATORI_DEFAULT = {
    SQUADRA_1[0]: "Destra",
    SQUADRA_1[1]: "Sinistra",
    SQUADRA_2[0]: "Destra",
    SQUADRA_2[1]: "Sinistra",
}

ESITI = ["Winner", "Errore forzato", "Errore non forzato"]
ESITO_IN_GIOCO = "In gioco"
ESITI_STATISTICHE = ESITI + [ESITO_IN_GIOCO]
COLPI = [
    "Vibora",
    "Smash",
    "Bandeja",
    "Rullo",
    "Volee dritto",
    "Volee rovescio",
    "Bajada",
    "Blocco",
    "Pallonetto",
    "Difesa dritto",
    "Difesa rovescio",
]
PUNTI_TENNIS = ["0", "15", "30", "40"]
SET_DA_VINCERE = 2  # Best of 3 set


class PadelTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("Padel — statistiche e punteggio")
        self.root.geometry("1080x820")
        self.root.minsize(900, 720)

        self.giocatori = SQUADRA_1 + SQUADRA_2
        if len(self.giocatori) != 4 or len(set(self.giocatori)) != 4:
            raise ValueError("Inserisci quattro nomi distinti nelle due squadre.")

        self.squadra_giocatore = {
            **{nome: 0 for nome in SQUADRA_1},
            **{nome: 1 for nome in SQUADRA_2},
        }

        # stats[giocatore][esito][colpo] = conteggio.
        # "In gioco" conta i colpi registrati con Continua scambio.
        self.stats = self._statistiche_vuote()

        # Stato del punteggio.
        self.punti = [0, 0]  # 0, 1, 2, 3 = 0, 15, 30, 40
        self.games = [0, 0]
        self.sets = [0, 0]
        self.punti_tiebreak = [0, 0]
        self.deuces_completati = 0
        self.fase_vantaggio = 0  # 0 = nessuno, 1 = primo, 2 = secondo
        self.star_point_pending = False
        self.set_scores = []
        self.partita_finita = False

        # Il battitore va impostato manualmente per ogni game. Il valore viene
        # fissato quando inizia il primo colpo dello scambio, così non cambia
        # a metà punto.
        self.server_var = tk.StringVar(value=SQUADRA_1[0])
        self.server_del_punto = None
        # La battuta parte da Destra a inizio game e poi alterna Destra/Sinistra
        # punto per punto. In un tie-break alterna a ogni punto senza reset.
        self.lato_servizio_corrente = "Destra"
        self.lato_servizio_del_punto = None
        self.lati_giocatori = {
            nome: LATI_GIOCATORI_DEFAULT.get(nome, "Destra") for nome in self.giocatori
        }
        self.var_lati_giocatori = {}
        self.menu_lati_giocatori = {}
        self.assist_stats = {nome: 0 for nome in self.giocatori}

        # Le azioni intermedie si accumulano qui finché non si chiude il punto.
        self.scambio_corrente = []
        self.punteggio_prima_scambio = None

        # Una voce in cronologia_punti per ogni punto concluso. Uno snapshot per
        # ogni azione permette di annullare anche un singolo colpo intermedio.
        self.cronologia_punti = []
        self._undo_stack = []

        self._crea_interfaccia()
        self._aggiorna_punteggio()

    def _statistiche_vuote(self):
        return {
            nome: {
                esito: {colpo: 0 for colpo in COLPI}
                for esito in ESITI_STATISTICHE
            }
            for nome in self.giocatori
        }

    def _crea_interfaccia(self):
        ttk.Label(
            self.root,
            text="PADEL TRACKER",
            font=("TkDefaultFont", 18, "bold"),
        ).pack(pady=(14, 8))

        score_frame = ttk.LabelFrame(self.root, text="Punteggio live", padding=12)
        score_frame.pack(fill="x", padx=18, pady=8)

        self.label_sets = ttk.Label(score_frame, font=("TkDefaultFont", 13, "bold"))
        self.label_sets.pack(pady=3)
        self.label_games = ttk.Label(score_frame, font=("TkDefaultFont", 12))
        self.label_games.pack(pady=3)
        self.label_punti = ttk.Label(score_frame, font=("TkDefaultFont", 12, "bold"))
        self.label_punti.pack(pady=3)
        self.label_stato = ttk.Label(
            score_frame, text="", font=("TkDefaultFont", 10, "italic")
        )
        self.label_stato.pack(pady=(3, 0))

        servizio_frame = ttk.LabelFrame(self.root, text="Servizio — dati per le statistiche", padding=8)
        servizio_frame.pack(fill="x", padx=18, pady=(3, 7))
        ttk.Label(servizio_frame, text="Giocatore al servizio nel game corrente:").pack(side="left", padx=(3, 8))
        self.menu_server = ttk.Combobox(
            servizio_frame,
            textvariable=self.server_var,
            values=self.giocatori,
            state="readonly",
            width=24,
        )
        self.menu_server.pack(side="left", padx=4)
        ttk.Label(
            servizio_frame,
            text="Seleziona il battitore prima del punto; durante lo scambio resta bloccato. Nel tie-break aggiornalo a ogni cambio turno.",
            wraplength=380,
        ).pack(side="left", padx=10)
        self.label_lato_servizio = ttk.Label(
            servizio_frame, text="Prossima battuta: Destra", font=("TkDefaultFont", 10, "bold")
        )
        self.label_lato_servizio.pack(side="right", padx=8)

        squadre_frame = ttk.Frame(self.root)
        squadre_frame.pack(fill="x", padx=18, pady=(10, 6))
        self.bottoni_giocatori = {}

        for colonna, (nome_squadra, nomi) in enumerate(
            ((NOMI_SQUADRE[0], SQUADRA_1), (NOMI_SQUADRE[1], SQUADRA_2))
        ):
            gruppo = ttk.LabelFrame(
                squadre_frame,
                text=f"{nome_squadra}: {' / '.join(nomi)}",
                padding=10,
            )
            gruppo.grid(row=0, column=colonna, sticky="nsew", padx=6)
            squadre_frame.columnconfigure(colonna, weight=1)

            for nome in nomi:
                riga_giocatore = ttk.Frame(gruppo)
                riga_giocatore.pack(fill="x", pady=4)
                bottone = ttk.Button(
                    riga_giocatore,
                    text=nome,
                    command=lambda n=nome: self._apri_inserimento(n),
                )
                bottone.pack(side="left", fill="x", expand=True, ipady=6)
                ttk.Label(riga_giocatore, text="Lato:").pack(side="left", padx=(10, 3))
                lato_var = tk.StringVar(value=self.lati_giocatori[nome])
                menu_lato = ttk.Combobox(
                    riga_giocatore,
                    textvariable=lato_var,
                    values=LATI_GIOCO,
                    state="readonly",
                    width=10,
                )
                menu_lato.pack(side="right")
                menu_lato.bind(
                    "<<ComboboxSelected>>",
                    lambda _event, n=nome, v=lato_var: self._cambia_lato_giocatore(n, v.get()),
                )
                self.var_lati_giocatori[nome] = lato_var
                self.menu_lati_giocatori[nome] = menu_lato
                self.bottoni_giocatori[nome] = bottone

        istruzioni = (
            "Imposta Destra/Sinistra per ciascun giocatore prima di iniziare; dopo il primo colpo i lati si bloccano. "
            "La battuta alterna Destra/Sinistra a ogni punto e riparte da Destra a ogni game. "
            "Per ogni colpo scegli prima il colpo; usa 'Continua scambio' oppure seleziona l'esito e premi 'Chiudi punto'."
        )
        ttk.Label(
            self.root,
            text=istruzioni,
            wraplength=900,
            justify="center",
        ).pack(padx=20, pady=(10, 6))

        self.label_scambio = ttk.Label(
            self.root,
            text="Scambio in corso: nessun colpo registrato",
            font=("TkDefaultFont", 11, "bold"),
            wraplength=900,
            justify="center",
        )
        self.label_scambio.pack(fill="x", padx=20, pady=7)

        azioni = ttk.Frame(self.root)
        azioni.pack(pady=10)

        self.bottone_annulla = ttk.Button(
            azioni,
            text="Annulla ultima azione",
            command=self._annulla_ultima_azione,
        )
        self.bottone_annulla.grid(row=0, column=0, padx=5, pady=4)

        ttk.Button(
            azioni,
            text="Visualizza statistiche",
            command=self._mostra_statistiche,
        ).grid(row=0, column=1, padx=5, pady=4)

        ttk.Button(
            azioni,
            text="Esporta statistiche JSON",
            command=self._esporta_json,
        ).grid(row=0, column=2, padx=5, pady=4)

        ttk.Button(azioni, text="Esci", command=self.root.destroy).grid(
            row=0, column=3, padx=5, pady=4
        )

    def _apri_inserimento(self, giocatore):
        """Mostra prima il menu colpo e poi l'esito conclusivo facoltativo."""
        if self.partita_finita:
            return

        finestra = tk.Toplevel(self.root)
        finestra.title(f"Registra colpo — {giocatore}")
        finestra.transient(self.root)
        finestra.grab_set()
        finestra.resizable(False, False)

        contenuto = ttk.Frame(finestra, padding=18)
        contenuto.pack(fill="both", expand=True)

        ttk.Label(
            contenuto,
            text=f"Giocatore: {giocatore}",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Label(contenuto, text="1. Colpo eseguito:").grid(
            row=1, column=0, sticky="w", pady=7, padx=(0, 12)
        )
        colpo_var = tk.StringVar(value=COLPI[0])
        menu_colpo = ttk.Combobox(
            contenuto,
            textvariable=colpo_var,
            values=COLPI,
            state="readonly",
            width=28,
        )
        menu_colpo.grid(row=1, column=1, sticky="ew", pady=7)

        ttk.Label(contenuto, text="2. Esito (solo se il punto finisce):").grid(
            row=2, column=0, sticky="w", pady=7, padx=(0, 12)
        )
        esito_var = tk.StringVar(value="")
        menu_esito = ttk.Combobox(
            contenuto,
            textvariable=esito_var,
            values=("", *ESITI),
            state="readonly",
            width=28,
        )
        menu_esito.grid(row=2, column=1, sticky="ew", pady=7)

        squadra_giocatore = self.squadra_giocatore[giocatore]
        compagni = [n for n in self.giocatori if self.squadra_giocatore[n] == squadra_giocatore and n != giocatore]
        ttk.Label(contenuto, text="3. Assist (facoltativo, solo per Winner):").grid(
            row=3, column=0, sticky="w", pady=7, padx=(0, 12)
        )
        assist_var = tk.StringVar(value="")
        menu_assist = ttk.Combobox(
            contenuto,
            textvariable=assist_var,
            values=("", *compagni),
            state="disabled",
            width=28,
        )
        menu_assist.grid(row=3, column=1, sticky="ew", pady=7)

        def aggiorna_assist(_event=None):
            if esito_var.get() == "Winner":
                menu_assist.configure(state="readonly")
            else:
                assist_var.set("")
                menu_assist.configure(state="disabled")

        menu_esito.bind("<<ComboboxSelected>>", aggiorna_assist)

        ttk.Label(
            contenuto,
            text=(
                "Continua scambio = il colpo resta in gioco e non assegna punti.\n"
                "Chiudi punto = registra Winner/Errore e aggiorna il punteggio."
            ),
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 12))

        def continua_scambio():
            colpo = colpo_var.get()
            if colpo not in COLPI:
                messagebox.showwarning(
                    "Colpo mancante", "Seleziona il colpo eseguito.", parent=finestra
                )
                return
            if esito_var.get():
                messagebox.showwarning(
                    "Scegli come registrare il colpo",
                    "Hai selezionato un esito finale. Per proseguire lo scambio, "
                    "svuota il menu Esito; per assegnare il punto, premi 'Chiudi punto'.",
                    parent=finestra,
                )
                return
            self._registra_colpo_in_gioco(giocatore, colpo)
            finestra.destroy()

        def chiudi_punto():
            colpo = colpo_var.get()
            esito = esito_var.get()
            if colpo not in COLPI:
                messagebox.showwarning(
                    "Colpo mancante", "Seleziona il colpo eseguito.", parent=finestra
                )
                return
            if esito not in ESITI:
                messagebox.showwarning(
                    "Esito mancante",
                    "Seleziona Winner, Errore forzato o Errore non forzato.",
                    parent=finestra,
                )
                return
            assistente = assist_var.get().strip() if esito == "Winner" else None
            self._concludi_punto(giocatore, esito, colpo, assistente=assistente or None)
            finestra.destroy()

        pulsanti = ttk.Frame(contenuto)
        pulsanti.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(
            pulsanti, text="Annulla", command=finestra.destroy
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            pulsanti, text="Chiudi punto", command=chiudi_punto
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            pulsanti, text="Continua scambio", command=continua_scambio
        ).pack(side="right")
        menu_colpo.focus_set()

    def _snapshot(self):
        """Copia lo stato mutabile necessario per annullare una singola azione."""
        return {
            "stats": copy.deepcopy(self.stats),
            "punti": self.punti.copy(),
            "games": self.games.copy(),
            "sets": self.sets.copy(),
            "punti_tiebreak": self.punti_tiebreak.copy(),
            "deuces_completati": self.deuces_completati,
            "fase_vantaggio": self.fase_vantaggio,
            "star_point_pending": self.star_point_pending,
            "set_scores": copy.deepcopy(self.set_scores),
            "partita_finita": self.partita_finita,
            "cronologia_punti": copy.deepcopy(self.cronologia_punti),
            "scambio_corrente": copy.deepcopy(self.scambio_corrente),
            "punteggio_prima_scambio": copy.deepcopy(self.punteggio_prima_scambio),
            "server_del_punto": self.server_del_punto,
            "lato_servizio_corrente": self.lato_servizio_corrente,
            "lato_servizio_del_punto": self.lato_servizio_del_punto,
            "assist_stats": copy.deepcopy(self.assist_stats),
        }

    def _ripristina_snapshot(self, snapshot):
        self.stats = copy.deepcopy(snapshot["stats"])
        self.punti = snapshot["punti"].copy()
        self.games = snapshot["games"].copy()
        self.sets = snapshot["sets"].copy()
        self.punti_tiebreak = snapshot["punti_tiebreak"].copy()
        self.deuces_completati = snapshot["deuces_completati"]
        self.fase_vantaggio = snapshot["fase_vantaggio"]
        self.star_point_pending = snapshot["star_point_pending"]
        self.set_scores = copy.deepcopy(snapshot["set_scores"])
        self.partita_finita = snapshot["partita_finita"]
        self.cronologia_punti = copy.deepcopy(snapshot["cronologia_punti"])
        self.scambio_corrente = copy.deepcopy(snapshot["scambio_corrente"])
        self.punteggio_prima_scambio = copy.deepcopy(snapshot["punteggio_prima_scambio"])
        self.server_del_punto = snapshot.get("server_del_punto")
        self.lato_servizio_corrente = snapshot.get("lato_servizio_corrente", "Destra")
        self.lato_servizio_del_punto = snapshot.get("lato_servizio_del_punto")
        self.assist_stats = copy.deepcopy(snapshot.get("assist_stats", self.assist_stats))

    def _cambia_lato_giocatore(self, nome, nuovo_lato):
        """Assegna il lato di gioco; se serve, scambia automaticamente il lato del compagno."""
        if nuovo_lato not in LATI_GIOCO:
            return
        self.lati_giocatori[nome] = nuovo_lato
        indice_squadra = self.squadra_giocatore[nome]
        compagno = next(
            n for n in self.giocatori
            if self.squadra_giocatore[n] == indice_squadra and n != nome
        )
        if self.lati_giocatori.get(compagno) == nuovo_lato:
            altro_lato = "Sinistra" if nuovo_lato == "Destra" else "Destra"
            self.lati_giocatori[compagno] = altro_lato
            self.var_lati_giocatori[compagno].set(altro_lato)

    def _giocatore_in_risposta(self, giocatore_al_servizio, lato_servizio):
        """Il ricevitore è il giocatore della coppia avversaria sul lato del servizio."""
        squadra_servizio = self.squadra_giocatore[giocatore_al_servizio]
        squadra_risposta = 1 - squadra_servizio
        ricevitori = [
            nome for nome in self.giocatori
            if self.squadra_giocatore[nome] == squadra_risposta
            and self.lati_giocatori.get(nome) == lato_servizio
        ]
        return ricevitori[0] if len(ricevitori) == 1 else None

    def _inizia_scambio_se_necessario(self):
        if not self.scambio_corrente and self.punteggio_prima_scambio is None:
            self.punteggio_prima_scambio = self._stato_punteggio()
            self.server_del_punto = self.server_var.get()
            self.lato_servizio_del_punto = self.lato_servizio_corrente

    def _registra_colpo_in_gioco(self, giocatore, colpo):
        """Registra un colpo intermedio senza assegnare il punto."""
        if self.partita_finita:
            return

        snapshot = self._snapshot()
        self._inizia_scambio_se_necessario()
        self.stats[giocatore][ESITO_IN_GIOCO][colpo] += 1
        self.scambio_corrente.append({
            "numero_azione_nello_scambio": len(self.scambio_corrente) + 1,
            "giocatore": giocatore,
            "colpo": colpo,
            "esito": ESITO_IN_GIOCO,
            "punto_concluso": False,
        })
        self._undo_stack.append({
            "snapshot": snapshot,
            "descrizione": f"{giocatore} — {ESITO_IN_GIOCO} — {colpo}",
        })
        self._aggiorna_punteggio()

    def _concludi_punto(self, giocatore, esito, colpo, assistente=None):
        """Registra il colpo decisivo, assegna il punto e salva il rally completo."""
        if self.partita_finita:
            return

        snapshot = self._snapshot()
        self._inizia_scambio_se_necessario()
        stato_prima_punto = copy.deepcopy(self.punteggio_prima_scambio)
        numero_set_completati_prima = len(self.set_scores)

        self.stats[giocatore][esito][colpo] += 1
        squadra_giocatore = self.squadra_giocatore[giocatore]
        squadra_punto = squadra_giocatore if esito == "Winner" else 1 - squadra_giocatore
        if esito != "Winner":
            assistente = None
        if assistente and (
            assistente not in self.giocatori
            or assistente == giocatore
            or self.squadra_giocatore.get(assistente) != squadra_giocatore
        ):
            assistente = None
        if assistente:
            self.assist_stats[assistente] = self.assist_stats.get(assistente, 0) + 1
        giocatore_al_servizio = self.server_del_punto or self.server_var.get()
        lato_servizio = self.lato_servizio_del_punto or self.lato_servizio_corrente
        squadra_servizio_idx = self.squadra_giocatore[giocatore_al_servizio]
        squadra_al_servizio = NOMI_SQUADRE[squadra_servizio_idx]
        giocatore_in_risposta = self._giocatore_in_risposta(giocatore_al_servizio, lato_servizio)
        squadra_in_risposta_idx = 1 - squadra_servizio_idx
        squadra_in_risposta = NOMI_SQUADRE[squadra_in_risposta_idx]
        games_prima = self.games.copy()

        azione_finale = {
            "numero_azione_nello_scambio": len(self.scambio_corrente) + 1,
            "giocatore": giocatore,
            "colpo": colpo,
            "esito": esito,
            "assistente": assistente,
            "punto_concluso": True,
        }
        self.scambio_corrente.append(azione_finale)

        self._assegna_punto(squadra_punto)
        # A ogni punto cambia il lato di battuta; dopo un game/set si riparte da Destra.
        if self.games != games_prima or len(self.set_scores) > numero_set_completati_prima:
            self.lato_servizio_corrente = "Destra"
        else:
            self.lato_servizio_corrente = "Sinistra" if lato_servizio == "Destra" else "Destra"
        stato_dopo = self._stato_punteggio()
        numero_punto = len(self.cronologia_punti) + 1

        # Una sola riga per punto, comoda da filtrare e importare in Excel.
        riga = (
            f"{stato_prima_punto['punti_game']} | {stato_prima_punto['game']} | "
            f"{stato_prima_punto['set']} | {giocatore} | {esito} | {colpo}"
            + (f" | Assist: {assistente}" if assistente else "")
        )
        azioni_scambio = copy.deepcopy(self.scambio_corrente)
        riepilogo_scambio = " -> ".join(
            f"{azione['giocatore']}: {azione['colpo']} ({azione['esito']})"
            for azione in azioni_scambio
        )

        record = {
            "punto_numero": numero_punto,
            "riga": riga,
            "punteggio_prima": stato_prima_punto,
            "azioni_scambio": azioni_scambio,
            "riepilogo_scambio": riepilogo_scambio,
            "giocatore": giocatore,
            "esito": esito,
            "colpo": colpo,
            "assistente": assistente,
            "squadra_che_fa_punto": NOMI_SQUADRE[squadra_punto],
            "giocatore_al_servizio": giocatore_al_servizio,
            "squadra_al_servizio": squadra_al_servizio,
            "lato_servizio": lato_servizio,
            "giocatore_in_risposta": giocatore_in_risposta,
            "squadra_in_risposta": squadra_in_risposta,
            "punto_vinto_in_servizio": squadra_punto == squadra_servizio_idx,
            "punto_vinto_in_risposta": squadra_punto != squadra_servizio_idx,
            "punto_vinto_in_risposta_da_giocatore": bool(
                giocatore_in_risposta
                and squadra_punto == self.squadra_giocatore[giocatore_in_risposta]
            ),
            "punteggio_dopo": stato_dopo,
        }
        if len(self.set_scores) > numero_set_completati_prima:
            record["set_completato_in_questa_azione"] = copy.deepcopy(self.set_scores[-1])

        self.cronologia_punti.append(record)
        self.scambio_corrente = []
        self.punteggio_prima_scambio = None
        self.server_del_punto = None
        self.lato_servizio_del_punto = None
        self._undo_stack.append({
            "snapshot": snapshot,
            "descrizione": f"{giocatore} — {esito} — {colpo}" + (f" — assist a {assistente}" if assistente else ""),
        })
        self._aggiorna_punteggio()

        if self.partita_finita:
            vincitrice = (
                f"{NOMI_SQUADRE[squadra_punto]} "
                f"({' / '.join(SQUADRA_1 if squadra_punto == 0 else SQUADRA_2)})"
            )
            messagebox.showinfo(
                "Partita terminata", f"Ha vinto {vincitrice}!", parent=self.root
            )

    def _assegna_punto(self, squadra):
        """Gestisce punteggio tennis, vantaggi, Star Point e tie-break."""
        # Tie-break sul 6-6: primo a 7 con almeno 2 punti di vantaggio.
        if self.games == [6, 6]:
            self.punti_tiebreak[squadra] += 1
            a, b = self.punti_tiebreak
            if max(a, b) >= 7 and abs(a - b) >= 2:
                punteggio_set = [7, 6] if squadra == 0 else [6, 7]
                self._vinto_set(squadra, punteggio_set)
            return

        # Se è attivo lo Star Point, il punto successivo decide il game.
        if self.star_point_pending:
            self._vinto_game(squadra)
            return

        # Un vantaggio vinto chiude il game. Se perso si torna pari; dopo il
        # secondo vantaggio perso si passa allo Star Point.
        if self.fase_vantaggio in (1, 2):
            squadra_con_vantaggio = 0 if self.punti[0] > self.punti[1] else 1
            fase_precedente = self.fase_vantaggio
            if squadra == squadra_con_vantaggio:
                self._vinto_game(squadra)
            else:
                self.punti = [3, 3]
                self.fase_vantaggio = 0
                if fase_precedente == 1:
                    self.deuces_completati = 1
                else:
                    self.deuces_completati = 2
                    self.star_point_pending = True
            return

        a, b = self.punti
        if a >= 3 and b >= 3 and a == b:
            self.punti[squadra] += 1
            self.fase_vantaggio = 1 if self.deuces_completati == 0 else 2
            return

        self.punti[squadra] += 1
        a, b = self.punti
        if max(a, b) >= 4 and abs(a - b) >= 2:
            self._vinto_game(squadra)

    def _vinto_game(self, squadra):
        self.games[squadra] += 1
        punteggio_game = self.games.copy()
        self.punti = [0, 0]
        self.punti_tiebreak = [0, 0]
        self.deuces_completati = 0
        self.fase_vantaggio = 0
        self.star_point_pending = False

        if (
            self.games[squadra] >= 6
            and self.games[squadra] - self.games[1 - squadra] >= 2
        ):
            self._vinto_set(squadra, punteggio_game)

    def _vinto_set(self, squadra, punteggio_set):
        self.set_scores.append({
            "numero_set": len(self.set_scores) + 1,
            NOMI_SQUADRE[0]: punteggio_set[0],
            NOMI_SQUADRE[1]: punteggio_set[1],
        })
        self.sets[squadra] += 1
        self.punti = [0, 0]
        self.punti_tiebreak = [0, 0]
        self.deuces_completati = 0
        self.fase_vantaggio = 0
        self.star_point_pending = False

        if self.sets[squadra] >= SET_DA_VINCERE:
            self.games = punteggio_set.copy()
            self.partita_finita = True
        else:
            self.games = [0, 0]

    def _punteggio_punti_compatto(self):
        if self.games == [6, 6]:
            return f"TB {self.punti_tiebreak[0]}-{self.punti_tiebreak[1]}"
        if self.star_point_pending:
            return "STAR POINT"

        a, b = self.punti
        if self.fase_vantaggio in (1, 2):
            vantaggio = f"AD{self.fase_vantaggio}"
            return f"{vantaggio}-40" if a > b else f"40-{vantaggio}"
        if a >= 3 and b >= 3 and a == b:
            return "40-40"
        return f"{PUNTI_TENNIS[min(a, 3)]}-{PUNTI_TENNIS[min(b, 3)]}"

    def _testo_punti_game(self):
        compatto = self._punteggio_punti_compatto()
        if self.games == [6, 6]:
            return f"Tie-break: {self.punti_tiebreak[0]} - {self.punti_tiebreak[1]}"
        if self.star_point_pending:
            return "STAR POINT — punto decisivo"
        if self.fase_vantaggio == 1:
            return f"{compatto} (primo vantaggio)"
        if self.fase_vantaggio == 2:
            return f"{compatto} (secondo vantaggio)"
        if self.punti[0] >= 3 and self.punti[1] >= 3 and self.punti[0] == self.punti[1]:
            deuce_numero = self.deuces_completati + 1
            return f"40 - 40 (parità {deuce_numero})"
        return compatto.replace("-", " - ")

    def _stato_punteggio(self):
        return {
            "punti_game": self._punteggio_punti_compatto(),
            "game": f"{self.games[0]}-{self.games[1]}",
            "set": f"{self.sets[0]}-{self.sets[1]}",
            "tie_break": self.games == [6, 6],
            "star_point": self.star_point_pending,
        }

    def _aggiorna_punteggio(self):
        parziali = ", ".join(
            f"{set_score[NOMI_SQUADRE[0]]}-{set_score[NOMI_SQUADRE[1]]}"
            for set_score in self.set_scores
        ) or "nessuno"
        self.label_sets.configure(
            text=(
                f"SET VINTI     {NOMI_SQUADRE[0]}  {self.sets[0]}  -  "
                f"{self.sets[1]}  {NOMI_SQUADRE[1]}     |     Parziali: {parziali}"
            )
        )
        self.label_games.configure(text=f"GAME    {self.games[0]}-{self.games[1]}")
        self.label_punti.configure(text=f"PUNTI    {self._testo_punti_game()}")
        self.label_lato_servizio.configure(text=f"Prossima battuta: {self.lato_servizio_corrente}")

        if self.partita_finita:
            stato = "Partita terminata"
        elif self.games == [6, 6]:
            stato = "Tie-break: primo a 7 punti con almeno 2 di vantaggio"
        elif self.star_point_pending:
            stato = "Star Point: il prossimo punto assegna il game"
        else:
            stato = "Sistema Star Point: due vantaggi, poi punto decisivo"
        self.label_stato.configure(text=stato)

        if self.scambio_corrente:
            descrizione = " → ".join(
                f"{azione['giocatore']}: {azione['colpo']}"
                for azione in self.scambio_corrente
            )
            self.label_scambio.configure(
                text=f"Scambio in corso ({len(self.scambio_corrente)} colpi): {descrizione}"
            )
        else:
            self.label_scambio.configure(text="Scambio in corso: nessun colpo registrato")

        stato_bottoni = "disabled" if self.partita_finita else "normal"
        for bottone in self.bottoni_giocatori.values():
            bottone.configure(state=stato_bottoni)
        self.bottone_annulla.configure(
            state="normal" if self._undo_stack else "disabled"
        )
        # Battitore fisso durante il punto; lato dei giocatori impostabile prima della partita.
        self.menu_server.configure(
            state="disabled" if self.scambio_corrente else "readonly"
        )
        lati_bloccati = bool(self.cronologia_punti or self.scambio_corrente)
        for menu_lato in self.menu_lati_giocatori.values():
            menu_lato.configure(state="disabled" if lati_bloccati else "readonly")

    def _annulla_ultima_azione(self):
        """Annulla l'ultima azione (colpo intermedio o chiusura del punto)."""
        if not self._undo_stack:
            return

        voce = self._undo_stack.pop()
        descrizione = voce["descrizione"]
        self._ripristina_snapshot(voce["snapshot"])
        self._aggiorna_punteggio()
        messagebox.showinfo(
            "Azione annullata",
            f"Annullata l'ultima azione: {descrizione}",
            parent=self.root,
        )

    def _mostra_statistiche(self):
        finestra = tk.Toplevel(self.root)
        finestra.title("Statistiche giocatori")
        finestra.geometry("850x480")

        colonne = ("giocatore", "esito", "colpo", "totale")
        tabella = ttk.Treeview(finestra, columns=colonne, show="headings")
        for colonna, titolo, larghezza in (
            ("giocatore", "Giocatore", 190),
            ("esito", "Esito", 180),
            ("colpo", "Colpo", 220),
            ("totale", "Totale", 90),
        ):
            tabella.heading(colonna, text=titolo)
            tabella.column(colonna, width=larghezza, anchor="center" if colonna == "totale" else "w")

        scrollbar = ttk.Scrollbar(finestra, orient="vertical", command=tabella.yview)
        tabella.configure(yscrollcommand=scrollbar.set)
        tabella.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=10)

        inserite = 0
        for giocatore in self.giocatori:
            for esito in ESITI_STATISTICHE:
                for colpo in COLPI:
                    totale = self.stats[giocatore][esito][colpo]
                    if totale:
                        tabella.insert("", "end", values=(giocatore, esito, colpo, totale))
                        inserite += 1
        if not inserite:
            tabella.insert("", "end", values=("Nessuna azione registrata", "", "", 0))

    def _esporta_json(self):
        percorso = filedialog.asksaveasfilename(
            parent=self.root,
            title="Esporta statistiche e cronologia punti",
            defaultextension=".json",
            filetypes=[("File JSON", "*.json")],
            initialfile="statistiche_padel.json",
        )
        if not percorso:
            return

        dati = {
            "squadre": {
                NOMI_SQUADRE[0]: SQUADRA_1,
                NOMI_SQUADRE[1]: SQUADRA_2,
            },
            "risultato": {
                "set_vinti": {
                    NOMI_SQUADRE[0]: self.sets[0],
                    NOMI_SQUADRE[1]: self.sets[1],
                },
                "game_corrente": {
                    NOMI_SQUADRE[0]: self.games[0],
                    NOMI_SQUADRE[1]: self.games[1],
                },
                "punti_correnti": self._punteggio_punti_compatto(),
                "set_completati": self.set_scores,
                "partita_finita": self.partita_finita,
            },
            "lati_giocatori": self.lati_giocatori,
            "assist_aggregate": self.assist_stats,
            "impostazioni_servizio": {
                "metodo": "Selezione manuale del giocatore al servizio prima del punto; nel tie-break a ogni cambio turno",
                "giocatore_selezionato_per_prossimo_punto": self.server_var.get(),
                "lato_servizio_prossimo_punto": self.lato_servizio_corrente,
                "alternanza_lato": "Destra/Sinistra a ogni punto; nei game nuovi si riparte da Destra",
                "metodo_individuazione_risposta": "Giocatore avversario assegnato al lato corrispondente al lato da cui parte il servizio",
                "nota": (
                    "Impostare il battitore all'inizio di ogni game e aggiornarlo a ogni cambio turno nel tie-break. I ruoli Destra/Sinistra si impostano "
                    "prima del primo colpo e vengono salvati nella cronologia per attribuire la risposta individuale."
                ),
            },
            "cronologia_punti": {
                "descrizione_riga": (
                    "Punteggio prima del punto | game | set vinti | "
                    "giocatore che chiude | esito finale | colpo finale"
                ),
                "colonne": [
                    "punto_numero",
                    "riga",
                    "punteggio_prima",
                    "azioni_scambio",
                    "riepilogo_scambio",
                    "giocatore",
                    "esito",
                    "colpo",
                    "squadra_che_fa_punto",
                    "assistente",
                    "giocatore_al_servizio",
                    "squadra_al_servizio",
                    "lato_servizio",
                    "giocatore_in_risposta",
                    "squadra_in_risposta",
                    "punto_vinto_in_servizio",
                    "punto_vinto_in_risposta",
                    "punto_vinto_in_risposta_da_giocatore",
                    "punteggio_dopo",
                    "set_completato_in_questa_azione",
                ],
                "dati": self.cronologia_punti,
            },
            "scambio_in_corso": {
                "punteggio_iniziale": self.punteggio_prima_scambio,
                "azioni": self.scambio_corrente,
                "nota": "Azioni non ancora concluse in un punto; non assegnano punti finché lo scambio non viene chiuso.",
            },
        }

        try:
            with open(percorso, "w", encoding="utf-8") as file:
                json.dump(dati, file, ensure_ascii=False, indent=2)
        except OSError as errore:
            messagebox.showerror("Errore di esportazione", str(errore), parent=self.root)
            return

        messagebox.showinfo(
            "Esportazione completata",
            f"Statistiche, scambi e cronologia salvati in:\n{percorso}",
            parent=self.root,
        )


def main():
    root = tk.Tk()
    PadelTracker(root)
    root.mainloop()


if __name__ == "__main__":
    main()
