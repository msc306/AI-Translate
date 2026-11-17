"use strict";

// Interface texts. Every entry lists the languages in the order of UI_LANGUAGES: de, en, es, fr.
// {name} marks a value that t() fills in.
const UI_LANGUAGES = ["de", "en", "es", "fr"];
const UI_LANGUAGE_NAMES = { de: "Deutsch", en: "English", es: "Español", fr: "Français" };

const TEXTS = {
  // ---------- title bar ----------
  title: ["Übersetzer", "Translator", "Traductor", "Traducteur"],
  ui_lang_title: ["Sprache der Oberfläche", "Interface language", "Idioma de la interfaz", "Langue de l’interface"],
  resizer_title: ["Breite ziehen", "Drag to change the width", "Arrastrar para cambiar el ancho", "Faire glisser pour changer la largeur"],
  dock_undock_title: ["Als normales Fenster lösen", "Detach as a normal window", "Separar como ventana normal", "Détacher en fenêtre normale"],
  dock_dock_title: ["Am Bildschirmrand andocken", "Dock to the screen edge", "Acoplar al borde de la pantalla", "Ancrer au bord de l’écran"],
  history: ["Verlauf", "History", "Historial", "Historique"],
  settings: ["Einstellungen", "Settings", "Ajustes", "Paramètres"],
  hide_title: ["Verbergen (bleibt im Infobereich)", "Hide (stays in the notification area)", "Ocultar (sigue en el área de notificación)", "Masquer (reste dans la zone de notification)"],

  // ---------- main view ----------
  source_title: ["Ausgangssprache", "Source language", "Idioma de origen", "Langue source"],
  target_title: ["Zielsprache", "Target language", "Idioma de destino", "Langue cible"],
  swap_title: ["Sprachen tauschen", "Swap languages", "Intercambiar idiomas", "Inverser les langues"],
  engine_title: ["Womit übersetzt wird", "What translates the text", "Con qué se traduce", "Avec quoi le texte est traduit"],
  size_title: ["Lokales Modell", "Local model", "Modelo local", "Modèle local"],
  size_small_opt: ["Klein (schnell)", "Small (fast)", "Pequeño (rápido)", "Petit (rapide)"],
  size_medium_opt: ["Mittel", "Medium", "Mediano", "Moyen"],
  size_large_opt: ["Groß (beste Qualität)", "Large (best quality)", "Grande (mejor calidad)", "Grand (meilleure qualité)"],
  size_small: ["Klein", "Small", "Pequeño", "Petit"],
  size_medium: ["Mittel", "Medium", "Mediano", "Moyen"],
  size_large: ["Groß", "Large", "Grande", "Grand"],
  style_title: ["Stil der Übersetzung", "Style of the translation", "Estilo de la traducción", "Style de la traduction"],
  engine_tip: [
    "Womit übersetzt wird: „Lokal“ rechnet auf diesem PC, ohne dass Text das Gerät verlässt. Die anderen Einträge sind Anbieter im Internet; welche hier erscheinen, legst du in den Einstellungen fest.",
    "What translates: “Local” runs on this PC and no text leaves the device. The other entries are online providers; you choose which ones appear here in the settings.",
    "Con qué se traduce: «Local» funciona en este PC y ningún texto sale del equipo. Las demás entradas son proveedores en internet; cuáles aparecen aquí se elige en los ajustes.",
    "Avec quoi traduire : « Local » tourne sur ce PC et aucun texte ne quitte l’appareil. Les autres entrées sont des fournisseurs en ligne ; tu choisis lesquels apparaissent ici dans les paramètres."],
  model_tip: [
    "Das Modell der gewählten Quelle. Lokal: klein ist schnell, groß übersetzt am besten, braucht aber mehr Grafikspeicher. Bei Anbietern im Internet unterscheiden sich die Modelle in Qualität, Tempo und Preis.",
    "The model of the chosen source. Local: small is fast, large translates best but needs more graphics memory. With online providers the models differ in quality, speed and price.",
    "El modelo de la fuente elegida. Local: el pequeño es rápido, el grande traduce mejor pero necesita más memoria gráfica. En los proveedores en internet los modelos difieren en calidad, velocidad y precio.",
    "Le modèle de la source choisie. Local : le petit est rapide, le grand traduit le mieux mais demande plus de mémoire graphique. Chez les fournisseurs en ligne, les modèles diffèrent en qualité, vitesse et prix."],
  style_tip: [
    "Ton der Übersetzung: neutral für den Alltag, förmlich für Briefe und Behörden, locker für Chats, wörtlich möglichst nah am Original.",
    "Tone of the translation: neutral for everyday use, formal for letters and officials, casual for chats, literal as close to the original as possible.",
    "Tono de la traducción: neutro para el día a día, formal para cartas y trámites, informal para chats, literal lo más cerca posible del original.",
    "Ton de la traduction : neutre pour le quotidien, formel pour les courriers et l’administration, décontracté pour les chats, littéral au plus près de l’original."],
  model_more: ["Weitere Modelle in den Einstellungen …", "More models in the settings …", "Más modelos en los ajustes …", "Plus de modèles dans les paramètres …"],
  model_taken: ["Modell übernommen: {model}", "Model taken: {model}", "Modelo elegido: {model}", "Modèle choisi : {model}"],
  model_default: ["Standardmodell", "Default model", "Modelo por defecto", "Modèle par défaut"],
  input_placeholder: [
    "Text eingeben oder einfügen, auch Screenshots (Strg+V) … (Strg+Enter übersetzt)",
    "Type or paste text, screenshots too (Ctrl+V) … (Ctrl+Enter translates)",
    "Escribe o pega texto, también capturas de pantalla (Ctrl+V) … (Ctrl+Intro traduce)",
    "Saisir ou coller du texte, captures d’écran aussi (Ctrl+V) … (Ctrl+Entrée traduit)"],
  translate: ["Übersetzen", "Translate", "Traducir", "Traduire"],
  cancel: ["Abbrechen", "Cancel", "Cancelar", "Annuler"],
  paste: ["Einfügen", "Paste", "Pegar", "Coller"],
  paste_title: [
    "Zwischenablage einfügen und übersetzen – Text oder Screenshot",
    "Paste the clipboard and translate – text or screenshot",
    "Pegar el portapapeles y traducir: texto o captura de pantalla",
    "Coller le presse-papiers et traduire – texte ou capture d’écran"],
  clear: ["Leeren", "Clear", "Vaciar", "Effacer"],
  clear_tip: [
    "Löscht Eingabe und Übersetzung und bricht eine laufende Übersetzung ab. Der Verlauf bleibt erhalten.",
    "Clears the input and the translation and stops a running translation. The history is kept.",
    "Borra la entrada y la traducción y detiene una traducción en curso. El historial se conserva.",
    "Efface la saisie et la traduction et arrête une traduction en cours. L’historique est conservé."],
  auto_tip: [
    "Übersetzt von selbst, kurz nachdem du aufgehört hast zu tippen oder Text eingefügt hast. Ausgeschaltet startet die Übersetzung erst mit „Übersetzen“ oder Strg+Enter.",
    "Translates by itself shortly after you stop typing or paste text. When switched off, translation only starts with “Translate” or Ctrl+Enter.",
    "Traduce por sí solo poco después de que dejes de escribir o pegues texto. Desactivado, la traducción solo empieza con «Traducir» o Ctrl+Intro.",
    "Traduit tout seul peu après la fin de la saisie ou un collage. Désactivé, la traduction ne démarre qu’avec « Traduire » ou Ctrl+Entrée."],
  speak_input_tip: [
    "Liest den eingegebenen Text mit einer Windows-Stimme vor. Ein zweiter Klick stoppt. Die Stimme lässt sich in den Einstellungen unter „Sprache“ festlegen.",
    "Reads the entered text aloud with a Windows voice. Click again to stop. The voice can be set in the settings under “Speech”.",
    "Lee en voz alta el texto introducido con una voz de Windows. Otro clic lo detiene. La voz se puede fijar en los ajustes, en «Voz».",
    "Lit le texte saisi à voix haute avec une voix Windows. Un second clic l’arrête. La voix se règle dans les paramètres, sous « Voix ».",
  ],
  mic_tip: [
    "Diktieren: klicken, sprechen, erneut klicken (oder Strg+Alt+M). Der erkannte Text wird eingefügt und übersetzt. Genauer mit whisper.cpp, das du in den Einstellungen unter „Sprache“ lädst.",
    "Dictate: click, speak, click again (or Ctrl+Alt+M). The recognised text is inserted and translated. More accurate with whisper.cpp, which you download in the settings under “Speech”.",
    "Dictar: haga clic, hable y vuelva a hacer clic (o Ctrl+Alt+M). El texto reconocido se inserta y se traduce. Más preciso con whisper.cpp, que se descarga en los ajustes, en «Voz».",
    "Dicter : cliquez, parlez, cliquez à nouveau (ou Ctrl+Alt+M). Le texte reconnu est inséré et traduit. Plus précis avec whisper.cpp, à télécharger dans les paramètres, sous « Voix ».",
  ],
  speak_output_tip: [
    "Liest die Übersetzung in der Zielsprache vor. Fehlt eine passende Stimme, lässt sie sich in Windows unter Zeit und Sprache → Sprachausgabe hinzufügen.",
    "Reads the translation aloud in the target language. If no matching voice exists, add one in Windows under Time & language → Speech.",
    "Lee la traducción en voz alta en el idioma de destino. Si falta una voz adecuada, añádala en Windows en Hora e idioma → Voz.",
    "Lit la traduction à voix haute dans la langue cible. S’il manque une voix adaptée, ajoutez-la dans Windows sous Heure et langue → Voix.",
  ],
  explain_tip: [
    "Erklärt, warum so übersetzt wurde, und schlägt andere Formulierungen vor, die sich mit einem Klick übernehmen lassen. Startet eine weitere Anfrage an das Modell.",
    "Explains why it was translated this way and suggests other wordings you can adopt with one click. Starts another request to the model.",
    "Explica por qué se tradujo así y propone otras formulaciones que puedes adoptar con un clic. Inicia otra consulta al modelo.",
    "Explique pourquoi la traduction est ainsi et propose d’autres formulations à reprendre d’un clic. Lance une nouvelle requête au modèle."],
  save_phrase_tip: [
    "Merkt sich Eingabe und Ausgabe als festes Paar. Kommt der Text wieder vor, wird genau diese Übersetzung verwendet. Vorher lässt sich die Ausgabe korrigieren.",
    "Remembers the input and the output as a fixed pair. When the text comes up again, exactly this translation is used. You can correct the output first.",
    "Recuerda la entrada y la salida como un par fijo. Cuando el texto vuelva a aparecer, se usará exactamente esta traducción. Antes puedes corregir la salida.",
    "Mémorise la saisie et le résultat comme une paire fixe. Quand le texte revient, c’est exactement cette traduction qui est utilisée. Le résultat peut être corrigé avant."],
  explanation_heading: ["Erklärung", "Explanation", "Explicación", "Explication"],
  senses_heading: ["Bedeutungen und Beispiele", "Meanings and examples", "Significados y ejemplos", "Sens et exemples"],
  example_prefix: ["Beispiel: ", "Example: ", "Ejemplo: ", "Exemple : "],
  auto_check: ["automatisch", "automatic", "automático", "automatique"],
  thorough: ["gründlich", "thorough", "a fondo", "approfondi"],
  thorough_title: [
    "Das Modell prüft seine Übersetzung in einem zweiten Durchgang und korrigiert Fehler. Dauert etwa doppelt so lang.",
    "The model checks its translation in a second pass and corrects mistakes. Takes about twice as long.",
    "El modelo revisa su traducción en una segunda pasada y corrige los errores. Tarda aproximadamente el doble.",
    "Le modèle vérifie sa traduction lors d’un second passage et corrige les erreurs. Dure environ deux fois plus longtemps."],
  clarify: ["bei Mehrdeutigkeit nachfragen", "ask when ambiguous", "preguntar si es ambiguo", "demander en cas d’ambiguïté"],
  clarify_title: [
    "Bei kurzen, mehrdeutigen Texten (z. B. „Bank“) erst fragen, was gemeint ist.",
    "For short, ambiguous texts (e.g. “bank”), first ask what is meant.",
    "Con textos cortos y ambiguos (p. ej. «banco»), preguntar primero qué se quiere decir.",
    "Pour les textes courts et ambigus (p. ex. « avocat »), demander d’abord ce qui est voulu."],
  output_title: [
    "Die Übersetzung lässt sich hier korrigieren und dann ins Phrasenbuch übernehmen",
    "The translation can be corrected here and then saved to the phrasebook",
    "La traducción se puede corregir aquí y guardar después en el libro de frases",
    "La traduction peut être corrigée ici puis enregistrée dans le carnet de phrases"],
  copy: ["Kopieren", "Copy", "Copiar", "Copier"],
  save_phrase: ["Ins Phrasenbuch", "To phrasebook", "Al libro de frases", "Vers le carnet"],
  explain: ["Erklären", "Explain", "Explicar", "Expliquer"],

  // ---------- first start ----------
  setup_title: ["Erste Schritte", "Getting started", "Primeros pasos", "Premiers pas"],
  setup_local: [
    "Lokal übersetzen: Der Text verlässt den PC nicht. Dafür werden die llama.cpp-Laufzeit und ein kleines Modell geladen (zusammen etwa 3,9 GB, einmalig). Wer LM Studio mit einem Modell installiert hat, braucht nichts zu laden.",
    "Translating locally: the text never leaves the PC. This needs the llama.cpp runtime and a small model (about 3.9 GB together, downloaded once). If LM Studio with a model is installed, nothing has to be downloaded.",
    "Traducir en local: el texto no sale del PC. Para ello se descargan el entorno llama.cpp y un modelo pequeño (unos 3,9 GB en total, una sola vez). Quien tenga LM Studio con un modelo no necesita descargar nada.",
    "Traduire en local : le texte ne quitte pas le PC. Il faut pour cela le moteur llama.cpp et un petit modèle (environ 3,9 Go au total, une seule fois). Si LM Studio est installé avec un modèle, rien n’est à télécharger."],
  setup_download: ["Laufzeit und Modell herunterladen", "Download runtime and model", "Descargar el entorno y el modelo", "Télécharger le moteur et le modèle"],
  setup_alt: [
    "Alternativ: In den Einstellungen unter „Anbieter im Internet“ ein Claude- oder ChatGPT-Abo oder einen API-Schlüssel einschalten.",
    "Alternatively: in the settings under “Online providers”, switch on a Claude or ChatGPT subscription or an API key.",
    "Como alternativa: en los ajustes, en «Proveedores en Internet», activa una suscripción de Claude o ChatGPT o una clave de API.",
    "Autre possibilité : dans les paramètres, sous « Fournisseurs en ligne », activer un abonnement Claude ou ChatGPT ou une clé API."],
  setup_open_settings: ["Einstellungen öffnen", "Open settings", "Abrir ajustes", "Ouvrir les paramètres"],
  setup_ready: ["Lokales Übersetzen ist eingerichtet.", "Local translation is set up.", "La traducción local está configurada.", "La traduction locale est configurée."],
  setup_missing: ["Für lokales Übersetzen fehlt noch {what}.", "Local translation still needs {what}.", "Para traducir en local todavía falta {what}.", "Pour traduire en local, il manque encore {what}."],
  setup_runtime: ["die llama.cpp-Laufzeit", "the llama.cpp runtime", "el entorno llama.cpp", "le moteur llama.cpp"],
  setup_model: ["ein Modell", "a model", "un modelo", "un modèle"],
  and: [" und ", " and ", " y ", " et "],
  setup_no_gpu: [
    "Auf diesem PC wurde keine NVIDIA-Grafikkarte gefunden. Lokale Modelle laufen deshalb nicht; übersetzen lässt sich über einen Anbieter im Internet.",
    "No NVIDIA graphics card was found on this PC, so local models cannot run; you can translate with an online provider.",
    "En este PC no se ha encontrado ninguna tarjeta gráfica NVIDIA. Por eso los modelos locales no funcionan; se puede traducir con un proveedor en Internet.",
    "Aucune carte graphique NVIDIA n’a été trouvée sur ce PC. Les modèles locaux ne fonctionnent donc pas ; la traduction reste possible avec un fournisseur en ligne."],
  downloading: ["Wird heruntergeladen …", "Downloading …", "Descargando …", "Téléchargement …"],

  // ---------- status line ----------
  stage_start: ["Starte …", "Starting …", "Iniciando …", "Démarrage …"],
  stage_vram_check: ["Prüfe freien Grafikspeicher …", "Checking free graphics memory …", "Comprobando la memoria gráfica libre …", "Vérification de la mémoire graphique libre …"],
  stage_loading: ["Lade Modell …", "Loading model …", "Cargando el modelo …", "Chargement du modèle …"],
  stage_translating: ["Übersetze …", "Translating …", "Traduciendo …", "Traduction …"],
  stage_retry: ["Ergebnis auffällig – versuche es noch einmal …", "Result looks odd – trying once more …", "Resultado extraño: lo intento de nuevo …", "Résultat suspect – nouvel essai …"],
  stage_unloading: ["Gebe Grafikspeicher frei …", "Freeing graphics memory …", "Liberando memoria gráfica …", "Libération de la mémoire graphique …"],
  stage_clarify: ["Prüfe, ob der Text eindeutig ist …", "Checking whether the text is unambiguous …", "Comprobando si el texto es inequívoco …", "Vérification de l’absence d’ambiguïté …"],
  stage_review: ["Prüfe die Übersetzung noch einmal …", "Checking the translation once more …", "Revisando la traducción otra vez …", "Nouvelle vérification de la traduction …"],
  stage_explaining: ["Erkläre die Übersetzung …", "Explaining the translation …", "Explicando la traducción …", "Explication de la traduction …"],
  stage_senses: ["Suche weitere Bedeutungen mit Beispielen …", "Looking up other meanings with examples …", "Buscando otros significados con ejemplos …", "Recherche d’autres sens avec exemples …"],
  stage_ocr: ["Lese den Text aus dem Bild …", "Reading the text from the image …", "Leyendo el texto de la imagen …", "Lecture du texte de l’image …"],
  progress: ["Übersetze … Abschnitt {chunk} von {chunks}", "Translating … section {chunk} of {chunks}", "Traduciendo … sección {chunk} de {chunks}", "Traduction … section {chunk} sur {chunks}"],
  cancelled: ["Abgebrochen.", "Cancelled.", "Cancelado.", "Annulé."],
  copied: ["Kopiert.", "Copied.", "Copiado.", "Copié."],
  nothing_to_save: ["Nichts zu speichern.", "Nothing to save.", "Nada que guardar.", "Rien à enregistrer."],
  phrase_taken: [
    "Ins Phrasenbuch übernommen – gilt ab der nächsten Übersetzung.",
    "Saved to the phrasebook – applies from the next translation on.",
    "Guardado en el libro de frases: se aplica a partir de la próxima traducción.",
    "Enregistré dans le carnet de phrases – s’applique dès la prochaine traduction."],
  no_translation_to_explain: [
    "Es gibt noch keine Übersetzung zum Erklären.",
    "There is no translation to explain yet.",
    "Todavía no hay ninguna traducción que explicar.",
    "Il n’y a pas encore de traduction à expliquer."],
  unknown_error: ["Unbekannter Fehler.", "Unknown error.", "Error desconocido.", "Erreur inconnue."],
  vram_insufficient: [
    "Nicht genug freier Grafikspeicher: {free} MB frei, benötigt {need} MB plus {reserve} MB Reserve. Es wurde nichts geladen. Wähle ein kleineres Modell oder versuche es später erneut.",
    "Not enough free graphics memory: {free} MB free, {need} MB needed plus {reserve} MB reserve. Nothing was loaded. Choose a smaller model or try again later.",
    "No hay suficiente memoria gráfica libre: {free} MB libres, se necesitan {need} MB más {reserve} MB de reserva. No se ha cargado nada. Elige un modelo más pequeño o inténtalo más tarde.",
    "Mémoire graphique libre insuffisante : {free} Mo libres, {need} Mo nécessaires plus {reserve} Mo de réserve. Rien n’a été chargé. Choisissez un modèle plus petit ou réessayez plus tard."],
  sidecar_exit: [
    "Der Übersetzungsdienst wurde beendet. Bitte die App neu starten.",
    "The translation service has stopped. Please restart the app.",
    "El servicio de traducción se ha detenido. Reinicia la aplicación.",
    "Le service de traduction s’est arrêté. Veuillez redémarrer l’application."],

  // ---------- result ----------
  skip_question: ["Egal, einfach übersetzen", "Never mind, just translate", "Da igual, traducir sin más", "Peu importe, traduire simplement"],
  no_particulars: ["Keine Besonderheiten.", "Nothing special to note.", "Nada especial que señalar.", "Rien de particulier à signaler."],
  alternatives: ["Alternativen", "Alternatives", "Alternativas", "Alternatives"],
  take: ["Übernehmen", "Use", "Usar", "Utiliser"],
  remarks: ["Anmerkungen", "Notes", "Notas", "Remarques"],
  ocr_note: [
    "Für {language} ist in Windows keine Texterkennung installiert, gelesen wurde mit „{used}“. Einzelne Zeichen können falsch sein – der erkannte Text lässt sich oben korrigieren.",
    "Windows has no text recognition installed for {language}; the image was read with “{used}”. Single characters may be wrong – the recognised text can be corrected above.",
    "Windows no tiene instalado el reconocimiento de texto para {language}; se ha leído con «{used}». Puede haber caracteres erróneos: el texto reconocido se puede corregir arriba.",
    "Windows n’a pas de reconnaissance de texte installée pour {language} ; l’image a été lue avec « {used} ». Certains caractères peuvent être faux – le texte reconnu peut être corrigé ci-dessus."],
  phrasebook: ["Phrasenbuch", "Phrasebook", "Libro de frases", "Carnet de phrases"],
  meta_local: ["lokal · {model}", "local · {model}", "local · {model}", "local · {model}"],
  meta_seconds: ["{seconds} s (davon Laden {load} s)", "{seconds} s (of which loading {load} s)", "{seconds} s (de ellos, {load} s de carga)", "{seconds} s (dont {load} s de chargement)"],
  meta_unloaded: ["Grafikspeicher freigegeben ({free} MB frei)", "graphics memory freed ({free} MB free)", "memoria gráfica liberada ({free} MB libres)", "mémoire graphique libérée ({free} Mo libres)"],
  meta_loaded: ["Modell noch geladen", "model still loaded", "modelo aún cargado", "modèle encore chargé"],
  meta_tokens: ["{input} + {output} Token", "{input} + {output} tokens", "{input} + {output} tokens", "{input} + {output} jetons"],
  review_changed: ["gründlich geprüft und korrigiert", "checked thoroughly and corrected", "revisado a fondo y corregido", "vérifié en profondeur et corrigé"],
  review_ok: ["gründlich geprüft", "checked thoroughly", "revisado a fondo", "vérifié en profondeur"],
  corrected_prefix: ["Korrigiert: ", "Corrected: ", "Corregido: ", "Corrigé : "],
  used_one: ["1 Eintrag aus dem Phrasengedächtnis verwendet", "1 phrase memory entry used", "Se ha usado 1 entrada de la memoria de frases", "1 entrée de la mémoire de phrases utilisée"],
  used_many: ["{count} Einträge aus dem Phrasengedächtnis verwendet", "{count} phrase memory entries used", "Se han usado {count} entradas de la memoria de frases", "{count} entrées de la mémoire de phrases utilisées"],
  match_whole: ["ganzer Text", "whole text", "texto completo", "texte entier"],
  match_exact: ["fester Eintrag", "fixed entry", "entrada fija", "entrée fixe"],
  match_similar: ["ähnlich", "similar", "similar", "similaire"],
  auto_detect: ["Automatisch erkennen", "Detect automatically", "Detectar automáticamente", "Détecter automatiquement"],
  auto: ["Automatisch", "Automatic", "Automático", "Automatique"],
  not_installed: ["nicht installiert", "not installed", "no instalado", "non installé"],

  // ---------- history ----------
  back: ["← Zurück", "← Back", "← Volver", "← Retour"],
  hist_clear: ["Alles löschen", "Delete all", "Borrar todo", "Tout supprimer"],
  hist_clear_title: ["Den ganzen Verlauf löschen", "Delete the whole history", "Borrar todo el historial", "Supprimer tout l’historique"],
  hist_clear_confirm: ["Wirklich alles löschen?", "Really delete everything?", "¿Borrar todo de verdad?", "Vraiment tout supprimer ?"],
  hist_filter: ["Im Verlauf suchen …", "Search the history …", "Buscar en el historial …", "Rechercher dans l’historique …"],
  hist_corrected: ["nur korrigierte", "corrected only", "solo corregidas", "corrigées uniquement"],
  hist_format_title: ["Dateiformat für den Export", "File format for the export", "Formato de archivo para la exportación", "Format de fichier pour l’export"],
  hist_export: ["Exportieren …", "Export …", "Exportar …", "Exporter …"],
  hist_export_title: [
    "Speichert die angezeigte Auswahl (alle oder nur korrigierte) als Datei",
    "Saves the shown selection (all or corrected only) as a file",
    "Guarda la selección mostrada (todas o solo las corregidas) en un archivo",
    "Enregistre la sélection affichée (toutes ou seulement les corrigées) dans un fichier"],
  hist_note: [
    "Die Übersetzung eines Eintrags lässt sich direkt hier korrigieren und mit ★ als Phrase speichern.",
    "The translation of an entry can be corrected right here and saved as a phrase with ★.",
    "La traducción de una entrada se puede corregir aquí mismo y guardar como frase con ★.",
    "La traduction d’une entrée peut être corrigée ici même et enregistrée comme phrase avec ★."],
  no_entries: ["Keine Einträge.", "No entries.", "No hay entradas.", "Aucune entrée."],
  corrected: ["korrigiert", "corrected", "corregida", "corrigée"],
  click_to_correct: ["Zum Korrigieren hineinklicken", "Click to correct", "Haz clic para corregir", "Cliquer pour corriger"],
  load_title: ["In den Übersetzer laden", "Load into the translator", "Cargar en el traductor", "Charger dans le traducteur"],
  from_history: ["aus dem Verlauf vom {time}", "from the history, {time}", "del historial, {time}", "de l’historique, {time}"],
  star_title: ["Als Phrase speichern (mit deiner Korrektur)", "Save as a phrase (with your correction)", "Guardar como frase (con tu corrección)", "Enregistrer comme phrase (avec votre correction)"],
  saved_as_phrase: [
    "Als Phrase gespeichert – gilt ab der nächsten Übersetzung.",
    "Saved as a phrase – applies from the next translation on.",
    "Guardada como frase: se aplica a partir de la próxima traducción.",
    "Enregistrée comme phrase – s’applique dès la prochaine traduction."],
  entry_delete_title: ["Eintrag löschen", "Delete entry", "Borrar entrada", "Supprimer l’entrée"],
  exported: ["{count} Einträge gespeichert: {path}", "{count} entries saved: {path}", "{count} entradas guardadas: {path}", "{count} entrées enregistrées : {path}"],

  // ---------- settings: languages ----------
  sec_languages: ["Sprachen", "Languages", "Idiomas", "Langues"],
  ui_language: ["Sprache der Oberfläche", "Interface language", "Idioma de la interfaz", "Langue de l’interface"],
  ui_language_hint: [
    "Gilt für Fenster, Meldungen und das Menü im Infobereich. Lässt sich auch oben neben dem Titel umstellen.",
    "Applies to the window, the messages and the menu in the notification area. Can also be changed at the top next to the title.",
    "Se aplica a la ventana, los mensajes y el menú del área de notificación. También se puede cambiar arriba, junto al título.",
    "S’applique à la fenêtre, aux messages et au menu de la zone de notification. Se change aussi en haut, à côté du titre."],
  translation_languages: ["Sprachen zum Übersetzen", "Languages to translate", "Idiomas para traducir", "Langues à traduire"],
  languages_hint: [
    "Angehakte Sprachen stehen im Hauptfenster zur Auswahl. Ein Sprachpaket ist dafür nicht nötig – es ergänzt feste Redewendungen für ein Sprachpaar.",
    "Ticked languages can be chosen in the main window. No language pack is needed for that – a pack adds fixed idioms for a language pair.",
    "Los idiomas marcados se pueden elegir en la ventana principal. No hace falta un paquete de idioma: este añade modismos fijos para un par de idiomas.",
    "Les langues cochées sont proposées dans la fenêtre principale. Aucun pack de langue n’est nécessaire – un pack ajoute des expressions figées pour une paire de langues."],
  min_two_languages: ["Mindestens zwei Sprachen müssen aktiv bleiben.", "At least two languages must stay active.", "Deben quedar activos al menos dos idiomas.", "Au moins deux langues doivent rester actives."],
  phrases_count_title: ["{count} Redewendungen im Phrasenbuch", "{count} idioms in the phrasebook", "{count} modismos en el libro de frases", "{count} expressions dans le carnet de phrases"],
  packs_title: ["Sprachpakete", "Language packs", "Paquetes de idioma", "Packs de langue"],
  pack_line: ["{count} Einträge · {origin}", "{count} entries · {origin}", "{count} entradas · {origin}", "{count} entrées · {origin}"],
  origin_user: ["selbst installiert", "installed by you", "instalado por ti", "installé par vous"],
  origin_bundled: ["mitgeliefert", "bundled", "incluido", "fourni"],
  pack_remove_title: ["Sprachpaket entfernen", "Remove language pack", "Quitar el paquete de idioma", "Supprimer le pack de langue"],
  pack_file: ["Sprachpaket aus Datei …", "Language pack from file …", "Paquete de idioma desde archivo …", "Pack de langue depuis un fichier …"],
  pack_file_hint: [
    "Ein Sprachpaket enthält feste Redewendungen für ein Sprachpaar, damit sie sinngemäß statt wörtlich übersetzt werden. Hier lässt sich ein Paket laden, das schon auf dem PC liegt (ZIP-Datei oder manifest.json) – zum Beispiel eines, das jemand mit „Eigene Phrasen exportieren“ erstellt hat.",
    "A language pack holds fixed idioms for a language pair, so that they are translated by meaning instead of word for word. Load a pack that is already on this PC here (ZIP file or manifest.json) – for example one that somebody created with “Export own phrases”.",
    "Un paquete de idioma contiene modismos fijos para un par de idiomas, para que se traduzcan por su sentido y no palabra por palabra. Aquí se carga un paquete que ya está en el PC (archivo ZIP o manifest.json), por ejemplo uno creado con «Exportar frases propias».",
    "Un pack de langue contient des expressions figées pour une paire de langues, afin qu’elles soient traduites selon le sens et non mot à mot. Chargez ici un pack déjà présent sur le PC (fichier ZIP ou manifest.json) – par exemple un pack créé avec « Exporter mes phrases »."],
  pack_url: ["https://… Adresse eines Sprachpakets (.zip oder manifest.json)", "https://… address of a language pack (.zip or manifest.json)", "https://… dirección de un paquete de idioma (.zip o manifest.json)", "https://… adresse d’un pack de langue (.zip ou manifest.json)"],
  pack_download_hint: [
    "Lädt ein Sprachpaket direkt aus dem Internet, ohne es vorher selbst zu speichern. Die Adresse zeigt auf eine ZIP-Datei oder auf die manifest.json eines Pakets, zum Beispiel {example}. Weitere Pakete und eine Vorlage liegen unter {source}.",
    "Downloads a language pack straight from the internet, without saving it yourself first. The address points to a ZIP file or to the manifest.json of a pack, for example {example}. More packs and a template are at {source}.",
    "Descarga un paquete de idioma directamente de Internet, sin guardarlo antes. La dirección apunta a un archivo ZIP o al manifest.json de un paquete, por ejemplo {example}. Hay más paquetes y una plantilla en {source}.",
    "Télécharge un pack de langue directement depuis Internet, sans l’enregistrer d’abord. L’adresse pointe vers un fichier ZIP ou vers le manifest.json d’un pack, par exemple {example}. D’autres packs et un modèle se trouvent sur {source}."],
  pack_example_use: ["Beispiel einsetzen", "Use the example", "Usar el ejemplo", "Utiliser l’exemple"],
  pack_installed: ["Sprachpaket „{pack}“ installiert.", "Language pack “{pack}” installed.", "Paquete de idioma «{pack}» instalado.", "Pack de langue « {pack} » installé."],
  pack_removed: ["Sprachpaket „{pack}“ entfernt.", "Language pack “{pack}” removed.", "Paquete de idioma «{pack}» quitado.", "Pack de langue « {pack} » supprimé."],
  installing: ["Installiere …", "Installing …", "Instalando …", "Installation …"],
  downloading_pack: ["Lade herunter …", "Downloading …", "Descargando …", "Téléchargement …"],

  // ---------- settings: local models ----------
  sec_local: ["Lokale Modelle", "Local models", "Modelos locales", "Modèles locaux"],
  local_hint: [
    "Für jede Größe lässt sich ein Modell wählen: aus den gefundenen Modellen auf diesem PC oder über „Durchsuchen“ eine beliebige GGUF-Datei.",
    "A model can be chosen for each size: from the models found on this PC or, with “Browse”, any GGUF file.",
    "Para cada tamaño se puede elegir un modelo: entre los encontrados en este PC o, con «Examinar», cualquier archivo GGUF.",
    "Un modèle peut être choisi pour chaque taille : parmi ceux trouvés sur ce PC ou, avec « Parcourir », n’importe quel fichier GGUF."],
  auto_named: ["Automatisch ({name})", "Automatic ({name})", "Automático ({name})", "Automatique ({name})"],
  model_option: ["{name} · {size} GB · braucht ca. {need} MB VRAM", "{name} · {size} GB · needs about {need} MB VRAM", "{name} · {size} GB · necesita unos {need} MB de VRAM", "{name} · {size} Go · nécessite env. {need} Mo de VRAM"],
  file_missing: ["{path} (Datei fehlt)", "{path} (file missing)", "{path} (falta el archivo)", "{path} (fichier manquant)"],
  browse: ["Durchsuchen …", "Browse …", "Examinar …", "Parcourir …"],
  model_link: ["Modell herunterladen ↗", "Download a model ↗", "Descargar un modelo ↗", "Télécharger un modèle ↗"],
  model_link_title: ["Öffnet {url} im Browser", "Opens {url} in the browser", "Abre {url} en el navegador", "Ouvre {url} dans le navigateur"],
  model_link_hint: [
    "Beispiel: {name} bei Hugging Face. Dort eine .gguf-Datei speichern (Q4_K_M ist ein guter Mittelweg) und sie über „Durchsuchen“ auswählen.",
    "Example: {name} on Hugging Face. Save a .gguf file there (Q4_K_M is a good middle ground) and pick it with “Browse”.",
    "Ejemplo: {name} en Hugging Face. Guarda allí un archivo .gguf (Q4_K_M es un buen término medio) y elígelo con «Examinar».",
    "Exemple : {name} sur Hugging Face. Enregistrez-y un fichier .gguf (Q4_K_M est un bon compromis) et choisissez-le avec « Parcourir »."],
  vram_line: ["Grafikspeicher: {free} von {total} MB frei", "Graphics memory: {free} of {total} MB free", "Memoria gráfica: {free} de {total} MB libres", "Mémoire graphique : {free} sur {total} Mo libres"],
  no_gpu: [
    "Keine NVIDIA-Grafikkarte gefunden. Lokale Modelle brauchen eine; ohne sie bleiben die Anbieter im Internet.",
    "No NVIDIA graphics card found. Local models need one; without it the online providers remain.",
    "No se ha encontrado ninguna tarjeta gráfica NVIDIA. Los modelos locales la necesitan; sin ella quedan los proveedores en Internet.",
    "Aucune carte graphique NVIDIA trouvée. Les modèles locaux en ont besoin ; sans elle, il reste les fournisseurs en ligne."],
  no_runtime: [
    "llama-server wurde nicht gefunden. Die Laufzeit lässt sich unten herunterladen.",
    "llama-server was not found. The runtime can be downloaded below.",
    "No se ha encontrado llama-server. El entorno se puede descargar más abajo.",
    "llama-server est introuvable. Le moteur peut être téléchargé ci-dessous."],
  installed: ["installiert", "installed", "instalado", "installé"],
  installed_button: ["Installiert", "Installed", "Instalado", "Installé"],
  download: ["Herunterladen", "Download", "Descargar", "Télécharger"],
  dl_amount: ["{done} von {total} MB", "{done} of {total} MB", "{done} de {total} MB", "{done} sur {total} Mo"],
  dl_running: ["lädt", "downloading", "descargando", "téléchargement"],
  dl_verifying: ["prüft die Datei", "verifying the file", "comprobando el archivo", "vérification du fichier"],
  dl_extracting: ["entpackt", "unpacking", "descomprimiendo", "décompression"],
  dl_done: ["fertig", "done", "terminado", "terminé"],
  dl_cancelled: ["abgebrochen", "cancelled", "cancelado", "annulé"],
  dl_error: ["Fehler", "error", "error", "erreur"],
  why_runtime: [
    "Wozu: Die Laufzeit ist das Programm, das ein Modell auf der Grafikkarte ausführt. Ohne sie startet kein lokales Modell.",
    "Why: the runtime is the program that runs a model on the graphics card. Without it no local model can start.",
    "Para qué: el entorno es el programa que ejecuta un modelo en la tarjeta gráfica. Sin él no arranca ningún modelo local.",
    "Pourquoi : le moteur est le programme qui exécute un modèle sur la carte graphique. Sans lui, aucun modèle local ne démarre."],
  why_model_small: [
    "Wozu: Das Modell übersetzt direkt auf diesem PC – ohne Internet, ohne Konto, und der Text verlässt den Rechner nicht. Es ist das kleinste und schnellste.",
    "Why: the model translates right on this PC – no internet, no account, and the text never leaves the computer. It is the smallest and fastest one.",
    "Para qué: el modelo traduce directamente en este PC, sin Internet ni cuenta, y el texto no sale del equipo. Es el más pequeño y rápido.",
    "Pourquoi : le modèle traduit directement sur ce PC – sans Internet, sans compte, et le texte ne quitte pas l’ordinateur. C’est le plus petit et le plus rapide."],
  downloads_hint: [
    "Downloads landen in {dir}. Jede Datei wird anhand ihrer Prüfsumme kontrolliert; ein abgebrochener Download setzt beim nächsten Mal fort.",
    "Downloads are stored in {dir}. Every file is verified by its checksum; an interrupted download continues next time.",
    "Las descargas se guardan en {dir}. Cada archivo se comprueba con su suma de verificación; una descarga interrumpida continúa la próxima vez.",
    "Les téléchargements sont enregistrés dans {dir}. Chaque fichier est vérifié par sa somme de contrôle ; un téléchargement interrompu reprend la fois suivante."],
  reserve: ["VRAM-Reserve für andere Programme (MB)", "VRAM reserve for other programs (MB)", "Reserva de VRAM para otros programas (MB)", "Réserve de VRAM pour les autres programmes (Mo)"],
  reserve_hint: [
    "So viel Grafikspeicher bleibt für Spiele, Browser und andere Programme frei. Ein Modell wird nur geladen, wenn danach noch diese Reserve übrig ist.",
    "This much graphics memory stays free for games, the browser and other programs. A model is only loaded if this reserve is still left afterwards.",
    "Esta cantidad de memoria gráfica queda libre para juegos, el navegador y otros programas. Un modelo solo se carga si después sigue quedando esta reserva.",
    "Cette quantité de mémoire graphique reste libre pour les jeux, le navigateur et les autres programmes. Un modèle n’est chargé que si cette réserve reste disponible ensuite."],
  keep: [
    "Modell nach Übersetzung geladen lassen (Sekunden, 0 = sofort entladen)",
    "Keep the model loaded after a translation (seconds, 0 = unload at once)",
    "Mantener el modelo cargado tras una traducción (segundos, 0 = descargar enseguida)",
    "Garder le modèle chargé après une traduction (secondes, 0 = décharger aussitôt)"],
  keep_hint: [
    "Solange das Modell geladen bleibt, startet die nächste Übersetzung ohne Wartezeit, es belegt aber Grafikspeicher. Bei 0 wird der Speicher nach jeder Übersetzung wieder frei.",
    "While the model stays loaded the next translation starts without waiting, but it occupies graphics memory. With 0 the memory is freed after every translation.",
    "Mientras el modelo sigue cargado, la siguiente traducción empieza sin espera, pero ocupa memoria gráfica. Con 0, la memoria se libera después de cada traducción.",
    "Tant que le modèle reste chargé, la traduction suivante démarre sans attente, mais il occupe de la mémoire graphique. Avec 0, la mémoire est libérée après chaque traduction."],

  // ---------- settings: online providers ----------
  sec_online: ["Anbieter im Internet", "Online providers", "Proveedores en Internet", "Fournisseurs en ligne"],
  online_hint: [
    "Alle standardmäßig aus. Ein eingeschalteter Anbieter erscheint in der Auswahl im Hauptfenster; solange er dort gewählt ist, wird der Text an ihn gesendet.",
    "All off by default. A provider that is switched on appears in the selection in the main window; while it is selected there, the text is sent to it.",
    "Todos desactivados de forma predeterminada. Un proveedor activado aparece en la selección de la ventana principal; mientras esté elegido allí, el texto se le envía.",
    "Tous désactivés par défaut. Un fournisseur activé apparaît dans la sélection de la fenêtre principale ; tant qu’il y est choisi, le texte lui est envoyé."],
  p_claude_sub: ["Claude-Abo (Pro/Max) über Claude Code", "Claude subscription (Pro/Max) via Claude Code", "Suscripción de Claude (Pro/Max) mediante Claude Code", "Abonnement Claude (Pro/Max) via Claude Code"],
  p_claude_api: ["Claude-API (Abrechnung nach Verbrauch)", "Claude API (billed by usage)", "API de Claude (facturación por uso)", "API Claude (facturation à l’usage)"],
  p_chatgpt_sub: ["ChatGPT-Abo (Plus/Pro) über Codex", "ChatGPT subscription (Plus/Pro) via Codex", "Suscripción de ChatGPT (Plus/Pro) mediante Codex", "Abonnement ChatGPT (Plus/Pro) via Codex"],
  p_openai_api: ["OpenAI-API oder kompatibler Anbieter", "OpenAI API or a compatible provider", "API de OpenAI o proveedor compatible", "API OpenAI ou fournisseur compatible"],
  p_openrouter: ["OpenRouter (viele Modelle mit einem Schlüssel)", "OpenRouter (many models with one key)", "OpenRouter (muchos modelos con una clave)", "OpenRouter (de nombreux modèles avec une clé)"],
  or_hint: [
    "OpenRouter vermittelt Modelle von Anthropic, OpenAI, Google, Mistral, Meta, DeepSeek und anderen über einen einzigen Schlüssel. Abgerechnet wird nach Verbrauch; manche Modelle sind kostenlos.",
    "OpenRouter gives access to models from Anthropic, OpenAI, Google, Mistral, Meta, DeepSeek and others with a single key. You pay per use; some models are free.",
    "OpenRouter da acceso a modelos de Anthropic, OpenAI, Google, Mistral, Meta, DeepSeek y otros con una sola clave. Se paga por uso; algunos modelos son gratuitos.",
    "OpenRouter donne accès aux modèles d'Anthropic, OpenAI, Google, Mistral, Meta, DeepSeek et d'autres avec une seule clé. Facturation à l'usage ; certains modèles sont gratuits.",
  ],
  or_get_key: ["Schlüssel bei OpenRouter holen", "Get a key at OpenRouter", "Obtener una clave en OpenRouter", "Obtenir une clé sur OpenRouter"],
  or_search: ["Modelle durchsuchen, z. B. claude, gemini, mistral", "Search models, e.g. claude, gemini, mistral", "Buscar modelos, p. ej. claude, gemini, mistral", "Rechercher des modèles, p. ex. claude, gemini, mistral"],
  or_free: ["nur kostenlose", "free only", "solo gratuitos", "gratuits seulement"],
  or_price_free: ["kostenlos", "free", "gratis", "gratuit"],
  or_price: ["{input} $ / {output} $ je Mio. Token", "{input} $ / {output} $ per M tokens", "{input} $ / {output} $ por M tokens", "{input} $ / {output} $ par M de jetons"],
  or_count: ["{shown} von {total} Modellen", "{shown} of {total} models", "{shown} de {total} modelos", "{shown} sur {total} modèles"],
  model: ["Modell", "Model", "Modelo", "Modèle"],
  haiku_fast: ["Haiku (schnell)", "Haiku (fast)", "Haiku (rápido)", "Haiku (rapide)"],
  chatgpt_model: ["Modell (leer = Standard des Abos)", "Model (empty = default of the subscription)", "Modelo (vacío = el predeterminado de la suscripción)", "Modèle (vide = celui par défaut de l’abonnement)"],
  api_key: ["API-Schlüssel", "API key", "Clave de API", "Clé API"],
  clear_key_title: ["Gespeicherten Schlüssel löschen", "Delete the stored key", "Borrar la clave guardada", "Supprimer la clé enregistrée"],
  address: ["Adresse", "Address", "Dirección", "Adresse"],
  load_models: ["Modelle laden", "Load models", "Cargar modelos", "Charger les modèles"],
  loading_models: ["Lade Modellliste …", "Loading the model list …", "Cargando la lista de modelos …", "Chargement de la liste des modèles …"],
  models_found: [
    "{count} Modelle gefunden – im Feld „Modell“ auswählbar.",
    "{count} models found – selectable in the “Model” field.",
    "{count} modelos encontrados: se pueden elegir en el campo «Modelo».",
    "{count} modèles trouvés – sélectionnables dans le champ « Modèle »."],
  ready: ["Bereit.", "Ready.", "Listo.", "Prêt."],
  key_saved: ["gespeichert (neuen Schlüssel eingeben zum Ersetzen)", "stored (type a new key to replace it)", "guardada (escribe una clave nueva para sustituirla)", "enregistrée (saisir une nouvelle clé pour la remplacer)"],
  key_env: ["leer = Umgebungsvariable {name}", "empty = environment variable {name}", "vacío = variable de entorno {name}", "vide = variable d’environnement {name}"],
  key_enter: ["Schlüssel eingeben", "Enter the key", "Introduce la clave", "Saisir la clé"],

  // ---------- settings: window ----------
  sec_window: ["Fenster", "Window", "Ventana", "Fenêtre"],
  monitor: ["Bildschirm", "Screen", "Pantalla", "Écran"],
  monitor_line: ["{index}: {name} – {width}×{height} bei ({x}, {y})", "{index}: {name} – {width}×{height} at ({x}, {y})", "{index}: {name} – {width}×{height} en ({x}, {y})", "{index} : {name} – {width}×{height} à ({x}, {y})"],
  primary: [" · Hauptbildschirm", " · main screen", " · pantalla principal", " · écran principal"],
  not_connected: ["{name} (nicht angeschlossen)", "{name} (not connected)", "{name} (no conectada)", "{name} (non connecté)"],
  edge: ["Seite", "Side", "Lado", "Côté"],
  right: ["rechts", "right", "derecha", "droite"],
  left: ["links", "left", "izquierda", "gauche"],
  width: ["Breite in %", "Width in %", "Ancho en %", "Largeur en %"],
  ontop: ["Gelöstes Fenster immer im Vordergrund", "Keep the detached window on top", "Ventana separada siempre visible", "Fenêtre détachée toujours au premier plan"],
  autostart: ["Mit Windows starten", "Start with Windows", "Iniciar con Windows", "Démarrer avec Windows"],
  hk_toggle: ["Tastenkürzel Anzeigen/Verbergen", "Shortcut to show/hide", "Atajo para mostrar/ocultar", "Raccourci afficher/masquer"],
  hk_clip: ["Tastenkürzel Zwischenablage übersetzen", "Shortcut to translate the clipboard", "Atajo para traducir el portapapeles", "Raccourci pour traduire le presse-papiers"],
  hk_mic: ["Tastenkürzel Spracheingabe (Start/Stopp)", "Shortcut for speech input (start/stop)", "Atajo para la entrada de voz (iniciar/detener)", "Raccourci pour la saisie vocale (démarrer/arrêter)"],
  hk_hint: [
    "Schreibweise wie Ctrl+Alt+T. Die Kürzel gelten überall in Windows, auch wenn das Fenster verborgen ist. Leer lassen schaltet ein Kürzel ab.",
    "Write them like Ctrl+Alt+T. The shortcuts work everywhere in Windows, even while the window is hidden. Leave a field empty to turn that shortcut off.",
    "Escríbalos como Ctrl+Alt+T. Los atajos funcionan en todo Windows, incluso con la ventana oculta. Deje un campo vacío para desactivar ese atajo.",
    "Notation comme Ctrl+Alt+T. Les raccourcis fonctionnent partout dans Windows, même fenêtre masquée. Laissez un champ vide pour désactiver ce raccourci."],

  // ---------- speech ----------
  mic_title: ["Spracheingabe: klicken, sprechen, nochmal klicken", "Speech input: click, speak, click again", "Entrada de voz: haga clic, hable y vuelva a hacer clic", "Saisie vocale : cliquer, parler, cliquer à nouveau"],
  mic_stop_title: ["Aufnahme beenden und Text erkennen", "Stop recording and recognise the text", "Detener la grabación y reconocer el texto", "Arrêter l’enregistrement et reconnaître le texte"],
  speak_input_title: ["Eingabe vorlesen", "Read the input aloud", "Leer la entrada en voz alta", "Lire le texte saisi à voix haute"],
  speak_output_title: ["Übersetzung vorlesen", "Read the translation aloud", "Leer la traducción en voz alta", "Lire la traduction à voix haute"],
  speak_stop_title: ["Vorlesen beenden", "Stop reading aloud", "Dejar de leer", "Arrêter la lecture"],
  stage_recording: ["Aufnahme läuft … zum Beenden 🎤 erneut klicken", "Recording … click 🎤 again to stop", "Grabando… haga clic de nuevo en 🎤 para detener", "Enregistrement… cliquez à nouveau sur 🎤 pour arrêter"],
  stage_transcribing: ["Erkenne die Sprache …", "Recognising speech …", "Reconociendo la voz…", "Reconnaissance de la parole…"],
  speech_done: ["Erkannt mit {engine} ({seconds} s Aufnahme).", "Recognised with {engine} ({seconds} s recording).", "Reconocido con {engine} ({seconds} s de grabación).", "Reconnu avec {engine} ({seconds} s d’enregistrement)."],
  nothing_to_speak: ["Es gibt nichts zum Vorlesen.", "There is nothing to read aloud.", "No hay nada que leer.", "Il n’y a rien à lire."],
  no_voice: ["Für {language} ist keine Windows-Stimme installiert; es liest die Standardstimme.", "No Windows voice is installed for {language}; the default voice reads instead.", "No hay ninguna voz de Windows instalada para {language}; lee la voz predeterminada.", "Aucune voix Windows n’est installée pour {language} ; la voix par défaut lit à la place."],
  sec_speech: ["Sprache (Mikrofon und Vorlesen)", "Speech (microphone and read-aloud)", "Voz (micrófono y lectura)", "Voix (microphone et lecture)"],
  speech_hint: [
    "🎤 nimmt über das Standardmikrofon von Windows auf und schreibt das Gesprochene ins Eingabefeld. Erkannt wird auf diesem PC – mit whisper.cpp (genau, mit Satzzeichen) oder, ohne Download, mit der Spracherkennung von Windows. 🔊 liest mit den Stimmen von Windows vor.",
    "🎤 records from the Windows default microphone and writes what you say into the input box. Recognition runs on this PC – with whisper.cpp (accurate, with punctuation) or, without any download, with the Windows speech recogniser. 🔊 reads aloud with the Windows voices.",
    "🎤 graba con el micrófono predeterminado de Windows y escribe lo dicho en el campo de entrada. El reconocimiento se hace en este PC: con whisper.cpp (preciso, con puntuación) o, sin descargar nada, con el reconocedor de voz de Windows. 🔊 lee en voz alta con las voces de Windows.",
    "🎤 enregistre avec le microphone par défaut de Windows et écrit ce que vous dites dans la zone de saisie. La reconnaissance se fait sur ce PC – avec whisper.cpp (précis, avec ponctuation) ou, sans téléchargement, avec la reconnaissance vocale de Windows. 🔊 lit à voix haute avec les voix de Windows."],
  speech_engine: ["Spracherkennung", "Speech recognition", "Reconocimiento de voz", "Reconnaissance vocale"],
  speech_engine_auto: ["Automatisch (whisper.cpp, sonst Windows)", "Automatic (whisper.cpp, else Windows)", "Automático (whisper.cpp; si no, Windows)", "Automatique (whisper.cpp, sinon Windows)"],
  speech_engine_whisper: ["whisper.cpp", "whisper.cpp", "whisper.cpp", "whisper.cpp"],
  speech_engine_windows: ["Windows-Spracherkennung", "Windows speech recognition", "Reconocimiento de voz de Windows", "Reconnaissance vocale de Windows"],
  speech_model: ["Sprachmodell (whisper.cpp)", "Speech model (whisper.cpp)", "Modelo de voz (whisper.cpp)", "Modèle vocal (whisper.cpp)"],
  speech_model_hint: [
    "Jede ggml-Datei von whisper.cpp passt, z. B. ggml-base-q5_1.bin (60 MB, schnell), ggml-small-q5_1.bin (180 MB, empfohlen) oder ggml-large-v3-turbo-q5_0.bin (550 MB, am genauesten). Dateien im Modellordner erscheinen automatisch in der Liste.",
    "Any whisper.cpp ggml file works, e.g. ggml-base-q5_1.bin (60 MB, fast), ggml-small-q5_1.bin (180 MB, recommended) or ggml-large-v3-turbo-q5_0.bin (550 MB, most accurate). Files in the models folder show up in the list automatically.",
    "Sirve cualquier archivo ggml de whisper.cpp, p. ej. ggml-base-q5_1.bin (60 MB, rápido), ggml-small-q5_1.bin (180 MB, recomendado) o ggml-large-v3-turbo-q5_0.bin (550 MB, el más preciso). Los archivos de la carpeta de modelos aparecen solos en la lista.",
    "Tout fichier ggml de whisper.cpp convient, p. ex. ggml-base-q5_1.bin (60 Mo, rapide), ggml-small-q5_1.bin (180 Mo, recommandé) ou ggml-large-v3-turbo-q5_0.bin (550 Mo, le plus précis). Les fichiers du dossier des modèles apparaissent automatiquement dans la liste."],
  speech_model_auto: ["Automatisch ({name})", "Automatic ({name})", "Automático ({name})", "Automatique ({name})"],
  speech_model_none: ["Automatisch (noch kein Modell)", "Automatic (no model yet)", "Automático (aún no hay modelo)", "Automatique (pas encore de modèle)"],
  speech_ready_whisper: ["whisper.cpp ist bereit.", "whisper.cpp is ready.", "whisper.cpp está listo.", "whisper.cpp est prêt."],
  speech_ready_windows: ["Ohne whisper.cpp erkennt Windows die Sprache (installiert: {languages}).", "Without whisper.cpp, Windows recognises speech (installed: {languages}).", "Sin whisper.cpp, Windows reconoce la voz (instalado: {languages}).", "Sans whisper.cpp, Windows reconnaît la parole (installé : {languages})."],
  speech_none: ["Keine Spracherkennung verfügbar – bitte whisper.cpp und ein Sprachmodell herunterladen.", "No speech recognition available – please download whisper.cpp and a speech model.", "No hay reconocimiento de voz: descargue whisper.cpp y un modelo de voz.", "Aucune reconnaissance vocale disponible – téléchargez whisper.cpp et un modèle vocal."],
  why_whisper: [
    "Wozu: whisper.cpp ist das Programm, das Gesprochenes auf diesem PC in Text umwandelt – genauer als die Windows-Erkennung und mit Satzzeichen. Es braucht zusätzlich ein Sprachmodell.",
    "Why: whisper.cpp is the program that turns speech into text on this PC – more accurate than Windows recognition and with punctuation. It also needs a speech model.",
    "Para qué: whisper.cpp es el programa que convierte la voz en texto en este PC, con más precisión que Windows y con puntuación. Necesita además un modelo de voz.",
    "Pourquoi : whisper.cpp est le programme qui transforme la parole en texte sur ce PC – plus précis que Windows et avec ponctuation. Il lui faut aussi un modèle vocal."],
  why_speech_model: [
    "Wozu: Das Sprachmodell enthält das Wissen für die Erkennung in rund 100 Sprachen. „small“ erkennt einen Satz in etwa zwei Sekunden.",
    "Why: the speech model holds the knowledge for recognition in about 100 languages. “small” recognises a sentence in about two seconds.",
    "Para qué: el modelo de voz contiene el conocimiento para reconocer unos 100 idiomas. «small» reconoce una frase en unos dos segundos.",
    "Pourquoi : le modèle vocal contient le savoir pour la reconnaissance d’environ 100 langues. « small » reconnaît une phrase en deux secondes environ."],
  voice: ["Stimme zum Vorlesen", "Voice for reading aloud", "Voz para leer", "Voix de lecture"],
  voice_auto: ["Automatisch (passend zur Sprache)", "Automatic (matching the language)", "Automático (según el idioma)", "Automatique (selon la langue)"],
  voice_hint: [
    "Weitere Stimmen lassen sich in Windows unter Einstellungen › Zeit und Sprache › Sprache installieren.",
    "More voices can be installed in Windows under Settings › Time & language › Language.",
    "Se pueden instalar más voces en Windows en Configuración › Hora e idioma › Idioma.",
    "D’autres voix s’installent dans Windows sous Paramètres › Heure et langue › Langue."],

  // ---------- settings: phrase memory ----------
  sec_memory: ["Phrasengedächtnis", "Phrase memory", "Memoria de frases", "Mémoire de phrases"],
  vector: [
    "Ähnliche Redewendungen finden (Vektordatenbank ChromaDB)",
    "Find similar idioms (vector database ChromaDB)",
    "Encontrar modismos parecidos (base de datos vectorial ChromaDB)",
    "Trouver des expressions proches (base vectorielle ChromaDB)"],
  mem_off: [
    "Aus – es werden nur wörtlich passende Einträge verwendet.",
    "Off – only entries that match literally are used.",
    "Desactivado: solo se usan las entradas que coinciden literalmente.",
    "Désactivé – seules les entrées correspondant littéralement sont utilisées."],
  mem_loading: [
    "Wird vorbereitet … (beim ersten Mal wird ein Sprachmodell für die Suche geladen, ca. 120 MB)",
    "Preparing … (the first time, a language model for the search is downloaded, about 120 MB)",
    "Preparando … (la primera vez se descarga un modelo de lenguaje para la búsqueda, unos 120 MB)",
    "Préparation … (la première fois, un modèle de langue pour la recherche est téléchargé, env. 120 Mo)"],
  mem_ready: ["Bereit – {count} Texte durchsuchbar.", "Ready – {count} texts searchable.", "Listo: {count} textos disponibles para la búsqueda.", "Prêt – {count} textes interrogeables."],
  mem_unavailable: [
    "Nicht verfügbar: {error} Wörtliche Einträge funktionieren weiter.",
    "Not available: {error} Literal entries keep working.",
    "No disponible: {error} Las entradas literales siguen funcionando.",
    "Indisponible : {error} Les entrées littérales continuent de fonctionner."],
  mem_no_chroma: ["ChromaDB ist nicht installiert.", "ChromaDB is not installed.", "ChromaDB no está instalado.", "ChromaDB n’est pas installé."],
  checks: [
    "Übersetzung prüfen und bei Auffälligkeiten einmal neu versuchen",
    "Check the translation and retry once if something looks odd",
    "Comprobar la traducción y reintentar una vez si algo resulta extraño",
    "Vérifier la traduction et réessayer une fois en cas d’anomalie"],
  history_save: [
    "Verlauf der Übersetzungen speichern (nur auf diesem PC)",
    "Save the translation history (on this PC only)",
    "Guardar el historial de traducciones (solo en este PC)",
    "Enregistrer l’historique des traductions (sur ce PC uniquement)"],
  ph_export: ["Eigene Phrasen exportieren …", "Export own phrases …", "Exportar frases propias …", "Exporter mes phrases …"],
  ph_export_title: [
    "Speichert deine eigenen Einträge als Sprachpaket, das andere installieren können",
    "Saves your own entries as a language pack that others can install",
    "Guarda tus propias entradas como paquete de idioma que otros pueden instalar",
    "Enregistre vos propres entrées comme pack de langue que d’autres peuvent installer"],
  lang_left: ["Sprache links", "Language on the left", "Idioma de la izquierda", "Langue de gauche"],
  lang_right: ["Sprache rechts", "Language on the right", "Idioma de la derecha", "Langue de droite"],
  ph_a: ["Redewendung", "Idiom", "Modismo", "Expression"],
  ph_b: ["Übersetzung", "Translation", "Traducción", "Traduction"],
  search: ["Suchen …", "Search …", "Buscar …", "Rechercher …"],
};

let uiLanguage = "de";

function t(key, values = {}) {
  const entry = TEXTS[key];
  if (!entry) return key;
  const text = entry[UI_LANGUAGES.indexOf(uiLanguage)] ?? entry[0];
  return text.replace(/\{(\w+)\}/g, (whole, name) => (name in values ? String(values[name]) : whole));
}

/** Name of a translation language in the interface language, e.g. "lt" -> "Litauisch" / "Lithuanian". */
function languageName(code, fallback) {
  try {
    const name = new Intl.DisplayNames([uiLanguage], { type: "language" }).of(code);
    if (name && name !== code) return name.charAt(0).toLocaleUpperCase(uiLanguage) + name.slice(1);
  } catch (err) { /* unknown code: use the fallback */ }
  return fallback || code.toUpperCase();
}

/** Fill every element marked with data-i18n (text), data-i18n-title or data-i18n-placeholder. */
function applyTexts(root = document) {
  document.documentElement.lang = uiLanguage;
  for (const node of root.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const node of root.querySelectorAll("[data-i18n-title]")) node.title = t(node.dataset.i18nTitle);
  for (const node of root.querySelectorAll("[data-i18n-placeholder]")) node.placeholder = t(node.dataset.i18nPlaceholder);
  for (const node of root.querySelectorAll("[data-i18n-aria-label]")) node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
}

function setTextLanguage(code) {
  uiLanguage = UI_LANGUAGES.includes(code) ? code : "de";
  return uiLanguage;
}
