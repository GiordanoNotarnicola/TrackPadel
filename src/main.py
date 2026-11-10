
import cv2
import numpy as np

image_path = "data/processed/frames/frame_0010.jpg"
image = cv2.imread(image_path)

if image is None:
    print("Errore: immagine non trovata")
    exit()

# Dimensioni originali
height, width = image.shape[:2]

# Parametri dello zoom
zoom = 1.0
view_left = 0.0
view_top = 0.0

# Memorizziamo i punti e i rettangoli
points = []
boxes = []


def render_image():
    # Creiamo una copia dell'immagine originale
    display_image = image.copy()

    # Disegniamo tutti i bounding box salvati
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(
            display_image,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2
        )

    # Matrice di trasformazione dello zoom
    matrix = np.array([
        [zoom, 0, -view_left * zoom],
        [0, zoom, -view_top * zoom]
    ], dtype=np.float32)

    # Visualizziamo la porzione ingrandita
    view = cv2.warpAffine(
        display_image,
        matrix,
        (width, height),
        flags=cv2.INTER_NEAREST
    )

    cv2.imshow("TrackPadel", view)


def mouse_callback(event, x, y, flags, param):
    global zoom, view_left, view_top, points, boxes

    # ZOOM CON ROTELLINA
    if event == cv2.EVENT_MOUSEWHEEL:

        # Coordinate originali sotto il cursore
        image_x = view_left + x / zoom
        image_y = view_top + y / zoom

        delta = cv2.getMouseWheelDelta(flags)

        if delta > 0:
            zoom = min(zoom * 1.25, 12.0)
        else:
            zoom = max(zoom / 1.25, 1.0)

        # Manteniamo il punto sotto il cursore
        # nella stessa posizione dello schermo
        view_left = image_x - x / zoom
        view_top = image_y - y / zoom

        # Limitiamo la visualizzazione ai bordi dell'immagine
        view_left = max(0, min(view_left, width - width / zoom))
        view_top = max(0, min(view_top, height - height / zoom))

        render_image()

    # RIPRISTINO VISUALIZZAZIONE COMPLETA
    elif event == cv2.EVENT_RBUTTONDOWN:
        zoom = 1.0
        view_left = 0.0
        view_top = 0.0
        render_image()

    # SELEZIONE CON DUE CLIC
    elif event == cv2.EVENT_LBUTTONDOWN:

        # Convertiamo le coordinate dello schermo
        # nelle coordinate dell'immagine originale
        original_x = int(view_left + x / zoom)
        original_y = int(view_top + y / zoom)

        points.append((original_x, original_y))

        print(f"Punto selezionato: X={original_x}, Y={original_y}")

        if len(points) == 2:

            x1, y1 = points[0]
            x2, y2 = points[1]

            # Normalizziamo le coordinate
            x1, x2 = sorted([x1, x2])
            y1, y2 = sorted([y1, y2])

            boxes.append((x1, y1, x2, y2))

            print(f"Bounding box: ({x1}, {y1}, {x2}, {y2})")

            points = []

            render_image()


# Creiamo la finestra
cv2.namedWindow("TrackPadel")

# Colleghiamo il callback del mouse
cv2.setMouseCallback("TrackPadel", mouse_callback)

# Mostriamo l'immagine iniziale
render_image()

cv2.waitKey(0)
cv2.destroyAllWindows()
