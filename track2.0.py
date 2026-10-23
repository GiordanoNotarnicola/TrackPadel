"""Padel Tracker: statistiche dei colpi, cronologia dei punti e punteggio live.

Flusso di registrazione:
1. Premi il pulsante del giocatore.
2. Premi un pulsante del colpo.
3. Continua selezionando giocatore e colpo per ogni azione dello scambio.
4. Premi Winner, Errore forzato o Errore non forzato per chiudere il punto.

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
# Configurazione fissa dei lati per distinguere il ricevitore nelle statistiche.
# Non è modificabile dalla finestra di tracking.
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
        self.root.geometry("1140x850")
        self.root.minsize(1050, 800)

        self.giocatori = SQUADRA_1 + SQUADRA_2
        if len(self.giocatori) != 4 or len(set(self.giocatori)) != 4:
            raise ValueError("Inserisci quattro nomi distinti nelle due squadre.")

        self.squadra_giocatore = {
            **{nome: 0 for nome in SQUADRA_1},
            **{nome: 1 for nome in SQUADRA_2},
        }

        # stats[giocatore][esito][colpo] = conteggio.
        # "In gioco" conta i colpi non conclusivi dello scambio.
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
        # I lati dei quattro giocatori sono configurati nelle costanti in cima
        # al file, non dall'interfaccia. Il lato di battuta alterna da solo.
        self.assist_stats = {nome: 0 for nome in self.giocatori}

        # Le azioni intermedie sono confermate quando si seleziona un colpo
        # successivo. L'ultimo colpo resta in attesa e diventa Winner/Errore
        # quando si preme uno dei pulsanti di chiusura punto.
        self.scambio_corrente = []
        self.azione_in_attesa = None
        self.giocatore_selezionato = None
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
        ).pack(pady=(12, 5))

        score_frame = ttk.LabelFrame(self.root, text="Punteggio live", padding=10)
        score_frame.pack(fill="x", padx=16, pady=5)
        self.label_sets = ttk.Label(score_frame, font=("TkDefaultFont", 12, "bold"))
        self.label_sets.pack(pady=2)
        self.label_games = ttk.Label(score_frame, font=("TkDefaultFont", 11))
        self.label_games.pack(pady=2)
        self.label_punti = ttk.Label(score_frame, font=("TkDefaultFont", 12, "bold"))
        self.label_punti.pack(pady=2)
        self.label_stato = ttk.Label(score_frame, text="", font=("TkDefaultFont", 9, "italic"))
        self.label_stato.pack(pady=(2, 0))

        servizio_frame = ttk.LabelFrame(self.root, text="Servizio", padding=7)
        servizio_frame.pack(fill="x", padx=16, pady=5)
        ttk.Label(servizio_frame, text="Giocatore al servizio per il prossimo punto:").pack(side="left", padx=(2, 8))
        self.menu_server = ttk.Combobox(
            servizio_frame,
            textvariable=self.server_var,
            values=self.giocatori,
            state="readonly",
            width=24,
        )
        self.menu_server.pack(side="left", padx=3)
        ttk.Label(
            servizio_frame,
            text="Aggiorna quando cambia il battitore; il lato di battuta alterna automaticamente.",
        ).pack(side="left", padx=8)

        squadre_frame = ttk.Frame(self.root)
        squadre_frame.pack(fill="x", padx=16, pady=(5, 3))
        self.bottoni_giocatori = {}
        for colonna, (nome_squadra, nomi) in enumerate(
            ((NOMI_SQUADRE[0], SQUADRA_1), (NOMI_SQUADRE[1], SQUADRA_2))
        ):
            gruppo = ttk.LabelFrame(
                squadre_frame,
                text=f"{nome_squadra}: {' / '.join(nomi)}",
                padding=8,
            )
            gruppo.grid(row=0, column=colonna, sticky="nsew", padx=5)
            squadre_frame.columnconfigure(colonna, weight=1)
            for nome in nomi:
                bottone = ttk.Button(
                    gruppo,
                    text=nome,
                    command=lambda n=nome: self._seleziona_giocatore(n),
                )
                bottone.pack(fill="x", pady=3, ipady=5)
                self.bottoni_giocatori[nome] = bottone

        self.label_selezione = ttk.Label(
            self.root,
            text="Passo 1: seleziona un giocatore.",
            font=("TkDefaultFont", 11, "bold"),
            anchor="center",
        )
        self.label_selezione.pack(fill="x", padx=16, pady=(5, 3))

        colpi_frame = ttk.LabelFrame(self.root, text="Colpo eseguito — premi un solo pulsante", padding=8)
        colpi_frame.pack(fill="x", padx=16, pady=4)
        self.bottoni_colpi = {}
        for indice, colpo in enumerate(COLPI):
            riga, colonna = divmod(indice, 4)
            bottone = ttk.Button(
                colpi_frame,
                text=colpo,
                command=lambda c=colpo: self._registra_colpo_selezionato(c),
                width=23,
            )
            bottone.grid(row=riga, column=colonna, sticky="ew", padx=4, pady=3, ipady=4)
            colpi_frame.columnconfigure(colonna, weight=1)
            self.bottoni_colpi[colpo] = bottone

        self.label_scambio = ttk.Label(
            self.root,
            text="Scambio in corso: nessun colpo registrato.",
            font=("TkDefaultFont", 10),
            wraplength=1000,
            justify="center",
        )
        self.label_scambio.pack(fill="x", padx=18, pady=6)

        esito_frame = ttk.LabelFrame(self.root, text="Fine punto — premi l'esito del colpo in attesa", padding=8)
        esito_frame.pack(fill="x", padx=16, pady=5)
        self.bottoni_esito = {}
        for esito, etichetta in (
            ("Winner", "WINNER"),
            ("Errore forzato", "ERRORE FORZATO"),
            ("Errore non forzato", "ERRORE NON FORZATO"),
        ):
            bottone = ttk.Button(
                esito_frame,
                text=etichetta,
                command=lambda e=esito: self._gestisci_esito(e),
                width=24,
            )
            bottone.pack(side="left", expand=True, fill="x", padx=4, ipady=6)
            self.bottoni_esito[esito] = bottone

        azioni = ttk.Frame(self.root)
        azioni.pack(pady=(5, 10))
        self.bottone_annulla = ttk.Button(
            azioni, text="Annulla ultima azione", command=self._annulla_ultima_azione
        )
        self.bottone_annulla.grid(row=0, column=0, padx=5, pady=3)
        ttk.Button(
            azioni, text="Visualizza statistiche", command=self._mostra_statistiche
        ).grid(row=0, column=1, padx=5, pady=3)
        ttk.Button(
            azioni, text="Esporta statistiche JSON", command=self._esporta_json
        ).grid(row=0, column=2, padx=5, pady=3)
        ttk.Button(azioni, text="Esci", command=self.root.destroy).grid(
            row=0, column=3, padx=5, pady=3
        )

    def _seleziona_giocatore(self, giocatore):
        """Seleziona chi esegue il prossimo colpo, senza registrare un'azione."""
        if self.partita_finita:
            return
        self.giocatore_selezionato = giocatore
        self._aggiorna_punteggio()

    def _registra_colpo_selezionato(self, colpo):
        """Registra il colpo selezionato; il precedente diventa un colpo in gioco."""
        if self.partita_finita:
            return
        if self.giocatore_selezionato not in self.giocatori:
            messagebox.showwarning(
                "Seleziona un giocatore",
                "Prima premi il pulsante del giocatore che ha eseguito il colpo.",
                parent=self.root,
            )
            return
        if colpo not in COLPI:
            return

        snapshot = self._snapshot()
        if self.azione_in_attesa is None:
            self._inizia_scambio_se_necessario()
        else:
            precedente = self.azione_in_attesa
            self.stats[precedente["giocatore"]][ESITO_IN_GIOCO][precedente["colpo"]] += 1
            self.scambio_corrente.append({
                "numero_azione_nello_scambio": len(self.scambio_corrente) + 1,
                "giocatore": precedente["giocatore"],
                "colpo": precedente["colpo"],
                "esito": ESITO_IN_GIOCO,
                "punto_concluso": False,
            })

        giocatore = self.giocatore_selezionato
        self.azione_in_attesa = {
            "numero_azione_nello_scambio": len(self.scambio_corrente) + 1,
            "giocatore": giocatore,
            "colpo": colpo,
            "esito": "In attesa di esito",
            "punto_concluso": False,
        }
        self._undo_stack.append({
            "snapshot": snapshot,
            "descrizione": f"{giocatore} — {colpo}",
        })
        # Ogni colpo richiede una selezione esplicita del giocatore, così si
        # riduce il rischio di attribuire per errore un colpo al compagno.
        self.giocatore_selezionato = None
        self._aggiorna_punteggio()

    def _gestisci_esito(self, esito):
        """Chiude il punto usando il colpo in attesa come colpo decisivo."""
        if self.partita_finita:
            return
        if not self.azione_in_attesa:
            messagebox.showwarning(
                "Nessun colpo da chiudere",
                "Seleziona un giocatore e premi il pulsante del colpo prima di assegnare l'esito.",
                parent=self.root,
            )
            return
        if esito == "Winner":
            self._chiedi_assist_winner()
        elif esito in ("Errore forzato", "Errore non forzato"):
            self._concludi_punto(esito)

    def _chiedi_assist_winner(self):
        """Consente di scegliere l'assist soltanto durante la chiusura con Winner."""
        if not self.azione_in_attesa:
            return
        giocatore = self.azione_in_attesa["giocatore"]
        colpo = self.azione_in_attesa["colpo"]
        squadra = self.squadra_giocatore[giocatore]
        compagni = [
            nome for nome in self.giocatori
            if self.squadra_giocatore[nome] == squadra and nome != giocatore
        ]

        finestra = tk.Toplevel(self.root)
        finestra.title("Winner — assist facoltativo")
        finestra.transient(self.root)
        finestra.grab_set()
        finestra.resizable(False, False)
        contenuto = ttk.Frame(finestra, padding=16)
        contenuto.pack(fill="both", expand=True)
        ttk.Label(
            contenuto,
            text=f"{giocatore} — {colpo}\nVuoi attribuire un assist al compagno?",
            font=("TkDefaultFont", 11, "bold"),
            justify="center",
        ).pack(pady=(0, 12))

        ttk.Button(
            contenuto,
            text="Winner senza assist",
            command=lambda: self._concludi_da_finestra_assist(finestra, None),
        ).pack(fill="x", pady=3)
        for compagno in compagni:
            ttk.Button(
                contenuto,
                text=f"Winner con assist di {compagno}",
                command=lambda c=compagno: self._concludi_da_finestra_assist(finestra, c),
            ).pack(fill="x", pady=3)
        ttk.Button(contenuto, text="Annulla", command=finestra.destroy).pack(pady=(8, 0))

    def _concludi_da_finestra_assist(self, finestra, assistente):
        try:
            finestra.grab_release()
        except tk.TclError:
            pass
        finestra.destroy()
        self._concludi_punto("Winner", assistente=assistente)

    def _snapshot(self):
        """Copia lo stato necessario per annullare l'ultima azione."""
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
            "azione_in_attesa": copy.deepcopy(self.azione_in_attesa),
            "giocatore_selezionato": self.giocatore_selezionato,
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
        self.azione_in_attesa = copy.deepcopy(snapshot.get("azione_in_attesa"))
        self.giocatore_selezionato = snapshot.get("giocatore_selezionato")
        self.punteggio_prima_scambio = copy.deepcopy(snapshot["punteggio_prima_scambio"])
        self.server_del_punto = snapshot.get("server_del_punto")
        self.lato_servizio_corrente = snapshot.get("lato_servizio_corrente", "Destra")
        self.lato_servizio_del_punto = snapshot.get("lato_servizio_del_punto")
        self.assist_stats = copy.deepcopy(snapshot.get("assist_stats", self.assist_stats))

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
        if not self.scambio_corrente and self.azione_in_attesa is None and self.punteggio_prima_scambio is None:
            self.punteggio_prima_scambio = self._stato_punteggio()
            self.server_del_punto = self.server_var.get()
            self.lato_servizio_del_punto = self.lato_servizio_corrente

    def _concludi_punto(self, esito, assistente=None):
        """Conclude il punto usando l'ultimo colpo premuto come azione decisiva."""
        if self.partita_finita or not self.azione_in_attesa:
            return

        snapshot = self._snapshot()
        azione_finale_pendente = copy.deepcopy(self.azione_in_attesa)
        giocatore = azione_finale_pendente["giocatore"]
        colpo = azione_finale_pendente["colpo"]
        self._inizia_scambio_se_necessario()
        stato_prima_punto = copy.deepcopy(self.punteggio_prima_scambio or self._stato_punteggio())
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
        azioni_scambio = copy.deepcopy(self.scambio_corrente) + [copy.deepcopy(azione_finale)]

        self._assegna_punto(squadra_punto)
        # La direzione di battuta alterna automaticamente. Dopo un game/set riparte da Destra.
        if self.games != games_prima or len(self.set_scores) > numero_set_completati_prima:
            self.lato_servizio_corrente = "Destra"
        else:
            self.lato_servizio_corrente = "Sinistra" if lato_servizio == "Destra" else "Destra"
        stato_dopo = self._stato_punteggio()
        numero_punto = len(self.cronologia_punti) + 1

        riga = (
            f"{stato_prima_punto['punti_game']} | {stato_prima_punto['game']} | "
            f"{stato_prima_punto['set']} | {giocatore} | {esito} | {colpo}"
            + (f" | Assist: {assistente}" if assistente else "")
        )
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
        self.azione_in_attesa = None
        self.giocatore_selezionato = None
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

        if self.partita_finita:
            stato = "Partita terminata"
        elif self.games == [6, 6]:
            stato = "Tie-break: primo a 7 punti con almeno 2 di vantaggio"
        elif self.star_point_pending:
            stato = "Star Point: il prossimo punto assegna il game"
        else:
            stato = "Star Point: dopo due vantaggi si gioca un punto decisivo"
        self.label_stato.configure(text=stato)

        if self.giocatore_selezionato:
            self.label_selezione.configure(
                text=f"Giocatore selezionato: {self.giocatore_selezionato}. Ora premi il pulsante del colpo."
            )
        else:
            self.label_selezione.configure(text="Passo 1: seleziona un giocatore.")

        azioni_visibili = list(self.scambio_corrente)
        if self.azione_in_attesa:
            azioni_visibili.append(self.azione_in_attesa)
        if azioni_visibili:
            descrizione = " → ".join(
                f"{azione['giocatore']}: {azione['colpo']}"
                for azione in azioni_visibili
            )
            attesa = ""
            if self.azione_in_attesa:
                attesa = (
                    f"\nEsito finale da attribuire a: {self.azione_in_attesa['giocatore']} — "
                    f"{self.azione_in_attesa['colpo']}"
                )
            self.label_scambio.configure(
                text=f"Scambio in corso ({len(azioni_visibili)} colpi): {descrizione}{attesa}"
            )
        else:
            self.label_scambio.configure(text="Scambio in corso: nessun colpo registrato.")

        partita_attiva = not self.partita_finita
        for nome, bottone in self.bottoni_giocatori.items():
            prefisso = "▶ " if nome == self.giocatore_selezionato else ""
            bottone.configure(text=f"{prefisso}{nome}", state="normal" if partita_attiva else "disabled")
        for bottone in self.bottoni_colpi.values():
            bottone.configure(
                state="normal" if partita_attiva and self.giocatore_selezionato else "disabled"
            )
        for bottone in self.bottoni_esito.values():
            bottone.configure(
                state="normal" if partita_attiva and self.azione_in_attesa else "disabled"
            )
        self.bottone_annulla.configure(state="normal" if self._undo_stack else "disabled")
        # Il battitore si può aggiornare solo tra i punti, non durante uno scambio.
        scambio_attivo = bool(self.scambio_corrente or self.azione_in_attesa)
        self.menu_server.configure(state="disabled" if scambio_attivo or self.partita_finita else "readonly")

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
            "statistiche_aggregate": self.stats,
            "impostazioni_servizio": {
                "metodo": "Selezione del giocatore al servizio manuale; il lato di battuta alterna automaticamente",
                "giocatore_selezionato_per_prossimo_punto": self.server_var.get(),
                "alternanza_lato": "Automatica: Destra/Sinistra alternati a ogni punto; nei game nuovi si riparte da Destra",
                "metodo_individuazione_risposta": "Il ricevitore è ricavato dal lato di battuta alternato e dalla configurazione LATI_GIOCATORI_DEFAULT in cima al file",
                "nota": (
                    "Il lato di battuta non è selezionabile dall'interfaccia. Per attribuire i punti in risposta al singolo giocatore, "
                    "modificare LATI_GIOCATORI_DEFAULT in cima al file se la coppia cambia lato abituale."
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
                "azioni": self.scambio_corrente + ([self.azione_in_attesa] if self.azione_in_attesa else []),
                "nota": "Lo scambio comprende i colpi confermati e, se presente, l'ultimo colpo in attesa di Winner/Errore. Nessun punto viene assegnato finché non si preme un esito.",
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