"""Build the user manual (Word) in English and French from the figures in docs/manual/figures.

    <python with python-docx 0.8.11> docs/manual/build_manual.py

Writes KRL_Generator_User_Manual_EN.docx and _FR.docx next to this script. The PDF versions
(and the table of contents) are made by make_pdf.ps1 with Word.
The text of both languages lives side by side below: every entry is (english, french).
"""
import os
import re

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")

NAVY = RGBColor(0x1E, 0x3A, 0x5F)
ACCENT = RGBColor(0x25, 0x63, 0xEB)
GREY = RGBColor(0x5B, 0x64, 0x70)
BODY_FONT = "Calibri"
HEAD_FONT = "Segoe UI Semibold"
NOTE_STYLES = {   # kind -> (fill, bar colour, label en, label fr)
    "tip": ("EAF2FE", "2563EB", "Tip", "Astuce"),
    "important": ("FFF6E5", "F59E0B", "Important", "Important"),
    "safety": ("FDECEC", "DC2626", "Safety", "Sécurité"),
}

# ---------------------------------------------------------------------------- content
# ("h1", en, fr) ("h2", en, fr) ("p", en, fr) ("bullets", [(en, fr), ...]) ("steps", [...])
# ("fig", name or (name_en, name_fr), width_cm, caption_en, caption_fr)
# ("note", kind, en, fr) ("table", [col widths cm], header (en, fr) list, rows of (en, fr) cells)
# ("code", text) ("pagebreak",)
# **bold** works in every text.

C = []


def h1(en, fr): C.append(("h1", en, fr))
def h2(en, fr): C.append(("h2", en, fr))
def p(en, fr): C.append(("p", en, fr))
def bullets(*items): C.append(("bullets", items))
def steps(*items): C.append(("steps", items))
def fig(name, width, en, fr): C.append(("fig", name, width, en, fr))
def note(kind, en, fr): C.append(("note", kind, en, fr))
def table(widths, header, *rows): C.append(("table", widths, header, rows))
def code(text): C.append(("code", text))
def pagebreak(): C.append(("pagebreak",))


def bi(name):
    return (name + "_en.png", name + "_fr.png")


# ----- 1 Introduction
h1("Introduction", "Introduction")
p("**KRL Generator** creates complete robot programs for continuous-fiber printing on the KUKA KR 6 R900 "
  "sixx. You describe the part (shape, size, number of turns and layers, head orientation), the program "
  "calculates the whole print path and writes a KUKA program file (**.src**). You copy that file to the "
  "robot controller on a USB stick and run it. Nothing has to be taught on the smartPAD.",
  "**KRL Generator** crée des programmes robot complets pour l'impression à fibre continue sur le KUKA "
  "KR 6 R900 sixx. Vous décrivez la pièce (forme, dimensions, nombre de tours et de couches, orientation de "
  "la tête), le programme calcule toute la trajectoire d'impression et écrit un fichier programme KUKA "
  "(**.src**). Vous copiez ce fichier sur la baie de commande avec une clé USB et vous l'exécutez. Aucun "
  "apprentissage de points au smartPAD n'est nécessaire.")
p("The fiber is never cut during a print, so the program always produces **one continuous path**: "
  "neighbouring loops (\"turns\") are joined by smooth transition moves, and the loops are stacked in "
  "height (\"layers\").",
  "La fibre n'est jamais coupée pendant une impression ; le programme produit donc toujours **une seule "
  "trajectoire continue** : les boucles voisines (« tours ») sont reliées par des mouvements de transition "
  "lisses, et les boucles sont empilées en hauteur (« couches »).")
fig(bi("diagram_workflow"), 16.5, "The workflow from the design to the print.",
    "Le déroulement, de la conception à l'impression.")
h2("What you can do with it", "Ce que vous pouvez faire")
bullets(("Generate **rounded-rectangle walls (cuboids)** and **tubes (cylinders)** with any number of turns "
         "and layers.",
         "Générer des **parois en rectangle arrondi (pavés)** et des **tubes (cylindres)** avec un nombre "
         "quelconque de tours et de couches."),
        ("Check the path before printing: a **top view**, a rotatable **3D view** and arrows that show where "
         "the head points.",
         "Contrôler la trajectoire avant l'impression : **vue de dessus**, **vue 3D** orientable et flèches "
         "indiquant la direction de la tête."),
        ("Add your own comments and approach moves to the program.",
         "Ajouter vos propres commentaires et mouvements d'approche au programme."),
        ("Export a ready-to-run **.src** file with the correct tool, base and speed settings (export profiles).",
         "Exporter un fichier **.src** prêt à l'emploi avec les bons réglages d'outil, de base et de vitesse "
         "(profils d'export)."),
        ("Save a print as a **project** and open it again later to repeat it exactly.",
         "Enregistrer une impression comme **projet** et la rouvrir plus tard pour la reproduire à "
         "l'identique."))
h2("About this manual", "À propos de ce manuel")
p("Chapter 3 gives a quick start (a first program in five minutes). The following chapters explain every "
  "part of the program in detail. Words in **bold** are the names you see on the screen. The program "
  "itself is in English; the French manual gives the English screen names.",
  "Le chapitre 3 propose une prise en main rapide (un premier programme en cinq minutes). Les chapitres "
  "suivants expliquent chaque partie du programme en détail. Les mots en **gras** sont les noms affichés à "
  "l'écran. Le programme est en anglais ; ce manuel français donne les noms anglais tels qu'ils "
  "apparaissent à l'écran.")
table([4.2, 12.3], [("Symbol", "Symbole"), ("Meaning", "Signification")],
      [("Tip", "Astuce"), ("A useful shortcut or good practice.", "Un raccourci utile ou une bonne pratique.")],
      [("Important", "Important"), ("Something that changes the result; read it before you continue.",
                                    "Un point qui modifie le résultat ; à lire avant de continuer.")],
      [("Safety", "Sécurité"), ("Something that protects people, the robot or the part.",
                                "Un point qui protège les personnes, le robot ou la pièce.")])

# ----- 2 Installation
h1("Installation and start", "Installation et démarrage")
h2("What you need", "Ce qu'il faut")
bullets(("A PC with **Windows 10 or 11 (64-bit)**. Nothing else has to be installed.",
         "Un PC sous **Windows 10 ou 11 (64 bits)**. Rien d'autre n'est à installer."),
        ("The two program files, always kept **together in the same folder**:",
         "Les deux fichiers du programme, toujours conservés **ensemble dans le même dossier** :"),
        ("    **KRL_Generator.exe**: the program.",
         "    **KRL_Generator.exe** : le programme."),
        ("    **export_profiles.json**: the robot settings (tool, base, speed) written into every exported "
         "program.",
         "    **export_profiles.json** : les réglages robot (outil, base, vitesse) écrits dans chaque "
         "programme exporté."))
note("important",
     "Copy both files. Without export_profiles.json the program still works, but it uses its built-in "
     "settings, which may not be the ones your lab uses.",
     "Copiez les deux fichiers. Sans export_profiles.json le programme fonctionne quand même, mais avec ses "
     "réglages intégrés, qui ne sont peut-être pas ceux de votre laboratoire.")
h2("Starting the program", "Lancer le programme")
steps(("Copy the folder with the two files to the PC (for example to the Desktop or to Documents).",
       "Copiez le dossier contenant les deux fichiers sur le PC (par exemple sur le Bureau ou dans "
       "Documents)."),
      ("Double-click **KRL_Generator.exe**. The main window opens after about two seconds.",
       "Double-cliquez sur **KRL_Generator.exe**. La fenêtre principale s'ouvre après deux secondes "
       "environ."),
      ("The first time, Windows may show **\"Windows protected your PC\"**. Click **More info**, then "
       "**Run anyway**. This happens because the program is not signed by a software publisher.",
       "La première fois, Windows peut afficher **« Windows a protégé votre ordinateur »**. Cliquez sur "
       "**Informations complémentaires**, puis sur **Exécuter quand même**. Cela vient du fait que le "
       "programme n'est pas signé par un éditeur de logiciels."))
note("tip",
     "Right-click KRL_Generator.exe and choose Send to > Desktop (create shortcut) to start it from the "
     "desktop. Keep the .exe itself next to export_profiles.json.",
     "Clic droit sur KRL_Generator.exe, puis Envoyer vers > Bureau (créer un raccourci) pour le lancer depuis "
     "le Bureau. Laissez le .exe lui-même à côté de export_profiles.json.")
h2("Checking the installation (self-test)", "Vérifier l'installation (auto-test)")
p("The program can check itself and show which robot settings it will write. Open a command prompt in the "
  "program folder (in File Explorer, type **cmd** in the address bar and press Enter) and run:",
  "Le programme peut se vérifier lui-même et afficher les réglages robot qu'il écrira. Ouvrez une invite de "
  "commandes dans le dossier du programme (dans l'Explorateur, tapez **cmd** dans la barre d'adresse puis "
  "Entrée) et lancez :")
code("KRL_Generator.exe --selftest")
p("A window reports whether a test cuboid and a test cylinder were generated and exported correctly, and "
  "shows the active tool (TCP), base, speed and rounding. The same report is saved as "
  "**selftest_report.txt** in the program folder.",
  "Une fenêtre indique si un pavé et un cylindre de test ont été générés et exportés correctement, et "
  "affiche l'outil (TCP), la base, la vitesse et l'arrondi actifs. Le même rapport est enregistré sous "
  "**selftest_report.txt** dans le dossier du programme.")

# ----- 3 Quick start
h1("Quick start: your first program", "Prise en main rapide : votre premier programme")
p("This example produces a rounded-rectangle wall of 3 turns and 3 layers with the default values.",
  "Cet exemple produit une paroi en rectangle arrondi de 3 tours et 3 couches avec les valeurs par défaut.")
steps(("Start the program. **Cuboid** is selected and all fields already contain working values.",
       "Lancez le programme. **Cuboid** est sélectionné et tous les champs contiennent déjà des valeurs "
       "utilisables."),
      ("Enter the size of your part in the **Size** card (centre, length, width, start height).",
       "Saisissez les dimensions de votre pièce dans la carte **Size** (centre, longueur, largeur, hauteur "
       "de départ)."),
      ("Set the number of turns and layers in the **Path** card.",
       "Réglez le nombre de tours et de couches dans la carte **Path**."),
      ("Click **Generate** (or press Ctrl+G). The path appears in the top view and the robot moves appear "
       "in the **KRL program** box.",
       "Cliquez sur **Generate** (ou Ctrl+G). La trajectoire apparaît dans la vue de dessus et les "
       "mouvements du robot dans la zone **KRL program**."),
      ("Click **3D View** to look at the stack from every side.",
       "Cliquez sur **3D View** pour observer l'empilement sous tous les angles."),
      ("Click **Export KRL...**, choose a file name such as **Wall_150x300** and save it as .src. Copy "
       "the file to the robot with a USB stick.",
       "Cliquez sur **Export KRL...**, choisissez un nom de fichier comme **Wall_150x300** et enregistrez "
       "en .src. Copiez le fichier sur le robot avec une clé USB."))
note("safety",
     "Run every new program first without fiber and resin, in T1 mode with a low override, and stop at the "
     "first point to check that the head is where you expect it (see chapter 16).",
     "Exécutez chaque nouveau programme d'abord sans fibre ni résine, en mode T1 avec un override faible, "
     "et arrêtez-vous au premier point pour vérifier que la tête est bien là où vous l'attendez (voir "
     "chapitre 16).")

# ----- 4 Main window
h1("The main window", "La fenêtre principale")
p("Everything is done in one window. The numbers in the picture match the table below.",
  "Tout se fait dans une seule fenêtre. Les numéros de l'image correspondent au tableau ci-dessous.")
fig("main_light.png", 16.5, "The main window after Generate (cuboid, 3 turns, 3 layers).",
    "La fenêtre principale après Generate (pavé, 3 tours, 3 couches).")
table([1.2, 4.3, 11.0], [("No.", "N°"), ("Part", "Élément"), ("What it does", "Rôle")],
      [("1", "1"), ("Menu bar", "Barre de menus"),
       ("File (projects, export), Edit (undo, comments, approach moves), Tools (3D view, export settings, "
        "advanced editors), Theme (light/dark), Help.",
        "File (projets, export), Edit (annuler, commentaires, approches), Tools (vue 3D, réglages "
        "d'export, éditeurs avancés), Theme (clair/sombre), Help (aide).")],
      [("2", "2"), ("Profile badge", "Badge du profil"),
       ("The export profile that will be used: its name, the tool (TCP) and the number of decimals. "
        "Change it with Tools > Export Settings (chapter 11).",
        "Le profil d'export qui sera utilisé : son nom, l'outil (TCP) et le nombre de décimales. Il se "
        "modifie avec Tools > Export Settings (chapitre 11).")],
      [("3", "3"), ("Shape", "Forme"), ("Choose Cuboid or Cylinder. Each shape keeps its own values.",
                                         "Choix entre Cuboid (pavé) et Cylinder (cylindre). Chaque forme "
                                         "garde ses propres valeurs.")],
      [("4", "4"), ("Size", "Dimensions"), ("Position and size of the first (inner) turn.",
                                           "Position et dimensions du premier tour (intérieur).")],
      [("5", "5"), ("Path", "Trajectoire"), ("Turn step, layer height, number of turns and layers.",
                                             "Pas entre tours, hauteur de couche, nombre de tours et de "
                                             "couches.")],
      [("6", "6"), ("Orientation & options", "Orientation et options"),
       ("Head angles A, B, C and the options auto-orient, C_DIS (and Helix for the cylinder).",
        "Angles de la tête A, B, C et les options auto-orientation, C_DIS (et Helix pour le cylindre).")],
      [("7", "7"), ("Generate", "Generate"), ("Calculates the path from the values on the left.",
                                              "Calcule la trajectoire à partir des valeurs de gauche.")],
      [("8", "8"), ("3D View, Export KRL..., Clear", "3D View, Export KRL..., Clear"),
       ("Open the 3D view, write the .src file, empty the program.",
        "Ouvrir la vue 3D, écrire le fichier .src, vider le programme.")],
      [("9", "9"), ("Top view", "Vue de dessus"), ("The path seen from above (zoom and move with the mouse).",
                                                   "La trajectoire vue d'en haut (zoom et déplacement à la "
                                                   "souris).")],
      [("10", "10"), ("Information chips", "Pastilles d'information"),
       ("Number of moves, path length, X/Y/Z range, head direction check, decimals.",
        "Nombre de mouvements, longueur, plages X/Y/Z, contrôle de la direction de la tête, décimales.")],
      [("11", "11"), ("KRL program", "Programme KRL"),
       ("The robot moves exactly as they will be exported. You can edit them and add lines.",
        "Les mouvements du robot tels qu'ils seront exportés. Vous pouvez les modifier et ajouter des "
        "lignes.")])

# ----- 5 Shapes
h1("Choosing and sizing the shape", "Choisir et dimensionner la forme")
p("Click **Cuboid** or **Cylinder** in the **Shape** card. The **Size** card changes to the fields of that "
  "shape. Switching back and forth keeps the values you typed for each shape.",
  "Cliquez sur **Cuboid** ou **Cylinder** dans la carte **Shape**. La carte **Size** affiche alors les champs "
  "de cette forme. Passer de l'une à l'autre conserve les valeurs saisies pour chaque forme.")
note("important",
     "All sizes describe the FIRST, INNER turn. The following turns are built outward from it, so the "
     "finished part is larger by about 2 × (Turns − 1) × E.",
     "Toutes les dimensions décrivent le PREMIER tour, le tour INTÉRIEUR. Les tours suivants sont "
     "construits vers l'extérieur ; la pièce finie est donc plus grande d'environ 2 × (Tours − 1) × E.")
h2("Cuboid (rounded rectangle)", "Pavé (rectangle arrondi)")
fig("size_cuboid.png", 9.0, "The Size card of the cuboid.", "La carte Size du pavé.")
fig(bi("diagram_cuboid"), 15.0, "Cuboid: meaning of the size fields, start point and seam.",
    "Pavé : signification des champs de dimensions, point de départ et jonction.")
table([4.0, 12.5], [("Field", "Champ"), ("Meaning", "Signification")],
      [("Centre X / Centre Y", "Centre X / Centre Y"),
       ("Centre of the rectangle in the robot base, in mm.", "Centre du rectangle dans la base robot, en mm.")],
      [("Length X", "Length X"), ("Size of the first turn along X, in mm.",
                                  "Dimension du premier tour selon X, en mm.")],
      [("Width Y", "Width Y"), ("Size of the first turn along Y, in mm.",
                                "Dimension du premier tour selon Y, en mm.")],
      [("Start Z", "Start Z"), ("Height of the first layer (the head height on the bed), in mm.",
                                "Hauteur de la première couche (hauteur de la tête sur le plateau), en mm.")],
      [("Corner radius", "Corner radius"),
       ("Radius of the rounded corners of the first turn. Leave it **blank** for an automatic value: 15 % "
        "of the shorter side (at least 2 mm, at most one third of the shorter side). The hint under the "
        "fields shows the value that will be used.",
        "Rayon des coins arrondis du premier tour. Laissez-le **vide** pour une valeur automatique : 15 % "
        "du plus petit côté (au moins 2 mm, au plus un tiers du plus petit côté). L'indication sous les "
        "champs affiche la valeur qui sera utilisée.")])
p("The print starts on the top edge next to the top-right corner and runs **counter-clockwise** (seen from "
  "above). The changes from one turn to the next and from one layer to the next all happen at the "
  "**top-right corner** (the seam), as smooth arcs that are tangent to the path. Every outer turn keeps the "
  "same corner centres, so its corners stay perfectly round.",
  "L'impression commence sur le bord supérieur, à côté du coin supérieur droit, et tourne dans le **sens "
  "antihoraire** (vu de dessus). Les passages d'un tour au suivant et d'une couche à la suivante se font "
  "tous au **coin supérieur droit** (la jonction), par des arcs lisses tangents à la trajectoire. Chaque tour "
  "extérieur garde les mêmes centres de coin ; ses coins restent donc parfaitement ronds.")
note("tip",
     "The program warns you when a corner radius is below 20 mm, because the head may not follow such a "
     "tight curve well. A radius larger than half the shorter side is refused.",
     "Le programme vous avertit lorsqu'un rayon de coin est inférieur à 20 mm, car la tête risque de mal "
     "suivre une courbe aussi serrée. Un rayon supérieur à la moitié du plus petit côté est refusé.")
h2("Cylinder (tube)", "Cylindre (tube)")
fig("size_cylinder.png", 9.0, "The Size card of the cylinder.", "La carte Size du cylindre.")
fig(bi("diagram_cylinder"), 15.0, "Cylinder: inner diameter, ring step, start point and seam.",
    "Cylindre : diamètre intérieur, pas entre anneaux, point de départ et jonction.")
table([4.0, 12.5], [("Field", "Champ"), ("Meaning", "Signification")],
      [("Centre X / Centre Y", "Centre X / Centre Y"), ("Centre of the tube in the robot base, in mm.",
                                                        "Centre du tube dans la base robot, en mm.")],
      [("Start Z", "Start Z"), ("Height of the first layer, in mm.", "Hauteur de la première couche, en mm.")],
      [("Inner diameter", "Inner diameter"), ("Diameter of the first (inner) ring, in mm.",
                                              "Diamètre du premier anneau (intérieur), en mm.")])
p("Each ring is a full circle made of four quarter arcs, counter-clockwise, starting on the **+X side** of "
  "the centre. The last quarter of each ring is the **seam**: there the path moves over to the next ring "
  "with two smooth arcs, or, on the last ring of a layer, climbs to the next layer.",
  "Chaque anneau est un cercle complet composé de quatre quarts d'arc, dans le sens antihoraire, en "
  "commençant du **côté +X** du centre. Le dernier quart de chaque anneau est la **jonction** : la "
  "trajectoire y passe à l'anneau suivant par deux arcs lisses ou, sur le dernier anneau d'une couche, "
  "monte à la couche suivante.")
fig("main_cylinder.png", 16.5, "A cylinder with 3 rings per layer (the purple quarter is the seam).",
    "Un cylindre de 3 anneaux par couche (le quart violet est la jonction).")
p("**Helix** (cylinder only, needs exactly 1 turn per layer): instead of climbing at the seam, the head "
  "rises evenly during the whole loop, like a spring. This gives a single-wall tube without a step. The "
  "last loop is flat so the top edge is level.",
  "**Helix** (cylindre uniquement, exige exactement 1 tour par couche) : au lieu de monter à la jonction, "
  "la tête s'élève régulièrement pendant toute la boucle, comme un ressort. On obtient un tube à paroi "
  "simple sans marche. La dernière boucle est plate pour que le bord supérieur soit horizontal.")
note("tip",
     "The program warns you when the smallest arc of the path (the inner radius minus about 0.7 × E, at the "
     "ring change) is below 20 mm. Diameters of 100 to 200 mm work well.",
     "Le programme vous avertit lorsque le plus petit arc de la trajectoire (le rayon intérieur moins "
     "environ 0,7 × E, au changement d'anneau) est inférieur à 20 mm. Des diamètres de 100 à 200 mm "
     "conviennent bien.")

# ----- 6 Path
h1("Path settings: turns and layers", "Réglages de trajectoire : tours et couches")
fig(bi("diagram_layers"), 15.0, "Cross-section through a wall of 3 turns and 3 layers.",
    "Coupe d'une paroi de 3 tours et 3 couches.")
table([4.4, 12.1], [("Field", "Champ"), ("Meaning", "Signification")],
      [("Turn step E (mm)", "Turn step E (mm)"),
       ("Distance between two neighbouring turns (centre to centre). Usually the width of the laid fiber "
        "or a little less, for example 2 mm.",
        "Distance entre deux tours voisins (d'axe en axe). En général la largeur de la fibre déposée ou un "
        "peu moins, par exemple 2 mm.")],
      [("Layer height (mm)", "Layer height (mm)"), ("Height step from one layer to the next.",
                                                    "Pas de hauteur d'une couche à la suivante.")],
      [("Turns per layer", "Turns per layer"),
       ("Number of concentric loops in each layer. The wall is about Turns × E wide.",
        "Nombre de boucles concentriques par couche. La paroi a une largeur d'environ Tours × E.")],
      [("Layers", "Layers"), ("Number of layers stacked in Z.", "Nombre de couches empilées en Z.")])
p("The numbers are **exact**: 3 turns and 3 layers give exactly 3 loops in each of 3 layers. The layers "
  "alternate so the fiber never has to jump: the first layer spirals **outward** (inner turn first), the "
  "second spirals **inward**, the third outward again, and so on.",
  "Les nombres sont **exacts** : 3 tours et 3 couches donnent exactement 3 boucles dans chacune des 3 "
  "couches. Les couches alternent pour que la fibre n'ait jamais à sauter : la première couche part **vers "
  "l'extérieur** (tour intérieur en premier), la deuxième **vers l'intérieur**, la troisième de nouveau vers "
  "l'extérieur, et ainsi de suite.")
note("tip",
     "In the program comments, layers and turns are counted from 0: the first layer is LAYER 0 and its "
     "first turn is T0. So layer 1 in the figure above is LAYER 0 in the program.",
     "Dans les commentaires du programme, les couches et les tours sont comptés à partir de 0 : la première "
     "couche est LAYER 0 et son premier tour T0. La couche 1 de la figure ci-dessus est donc LAYER 0 dans le "
     "programme.")
p("The total height of the print is Start Z + (Layers − 1) × Layer height. The information chips under the "
  "top view show the resulting Z range after Generate.",
  "La hauteur totale de l'impression est Start Z + (Couches − 1) × Hauteur de couche. Les pastilles "
  "d'information sous la vue de dessus affichent la plage Z obtenue après Generate.")

# ----- 7 Orientation
h1("Head orientation and options", "Orientation de la tête et options")
fig("left_panel.png", 7.5, "All input cards of the cuboid.", "Toutes les cartes de saisie du pavé.")
h2("The angles A, B and C", "Les angles A, B et C")
p("A, B and C are the KUKA orientation angles of the head in degrees (rotation about Z, then Y, then X).",
  "A, B et C sont les angles d'orientation KUKA de la tête, en degrés (rotation autour de Z, puis Y, "
  "puis X).")
table([3.2, 13.3], [("Angle", "Angle"), ("Use", "Utilisation")],
      [("A", "A"), ("Turns the head about the vertical axis. With auto-orient (below) it is calculated for "
                    "you; the value typed here is then only used where no direction exists yet.",
                    "Fait tourner la tête autour de l'axe vertical. Avec l'auto-orientation (voir plus bas) "
                    "il est calculé automatiquement ; la valeur saisie ne sert alors qu'aux points sans "
                    "direction connue.")],
      [("B / Tilt", "B / Tilt"), ("Tilt of the head. It is written to every move exactly as typed (no "
                                  "limits). 0 = the head is upright.",
                                  "Inclinaison de la tête. Elle est écrite telle quelle dans chaque "
                                  "mouvement (sans limite). 0 = tête droite.")],
      [("C", "C"), ("Third angle, written to every move as typed (180 for the current head).",
                    "Troisième angle, écrit tel quel dans chaque mouvement (180 pour la tête actuelle).")])
h2("A follows the travel direction (auto-orient)", "A suit la direction de déplacement (auto-orientation)")
fig(bi("diagram_head"), 15.0, "With auto-orient, A turns with the path so the roller leads and the UV lamp "
    "trails.", "Avec l'auto-orientation, A tourne avec la trajectoire : le rouleau précède et la lampe UV suit.")
p("When **A follows the travel direction (auto-orient)** is ticked (the default), A is set at every move so "
  "the head always faces the way it travels: constant along straight edges and turning smoothly through the "
  "corners. The roller then presses the fiber straight ahead and the UV lamp always trails behind it.",
  "Lorsque **A follows the travel direction (auto-orient)** est cochée (par défaut), A est réglé à chaque "
  "mouvement pour que la tête soit toujours tournée dans le sens du déplacement : constant le long des "
  "bords droits et tournant progressivement dans les coins. Le rouleau presse alors la fibre droit devant "
  "lui et la lampe UV le suit toujours.")
p("Untick it only for special tests: then the A, B and C values typed are written to every move "
  "unchanged.",
  "Ne la décochez que pour des essais particuliers : les valeurs A, B et C saisies sont alors écrites "
  "telles quelles dans chaque mouvement.")
h2("Approximate moves on export (C_DIS)", "Approximate moves on export (C_DIS)")
p("When ticked (the default), every path move in the exported file gets **C_DIS**. The robot then blends "
  "smoothly from one move into the next instead of stopping at each point. Stops leave resin blobs on the "
  "part, so keep this on for printing. The blending distance comes from the export profile ($APO.CDIS, "
  "5 mm).",
  "Lorsqu'elle est cochée (par défaut), chaque mouvement de trajectoire du fichier exporté reçoit "
  "**C_DIS**. Le robot enchaîne alors les mouvements en continu au lieu de s'arrêter à chaque point. Les "
  "arrêts laissent des gouttes de résine sur la pièce : laissez donc cette option active pour imprimer. La "
  "distance d'approximation vient du profil d'export ($APO.CDIS, 5 mm).")
note("important",
     "The robot only blends in continuous run. In single-step mode (step by step on the smartPAD) it still "
     "stops at every point; that is normal.",
     "Le robot n'approxime qu'en marche continue. En mode pas à pas (au smartPAD) il s'arrête toujours à "
     "chaque point ; c'est normal.")
h2("Helix", "Helix")
p("Only shown for the cylinder; see chapter 5.2.", "Affiché uniquement pour le cylindre ; voir le "
  "chapitre 5.2.")

# ----- 8 Checking
h1("Checking the path", "Contrôler la trajectoire")
p("Always look at the path before you export it. Three tools help you: the top view, the information chips "
  "and the 3D view.",
  "Regardez toujours la trajectoire avant de l'exporter. Trois outils vous aident : la vue de dessus, les "
  "pastilles d'information et la vue 3D.")
h2("Top view", "Vue de dessus")
fig("topview.png", 14.0, "The top view with its legend.", "La vue de dessus et sa légende.")
bullets(("**Mouse wheel**: zoom in and out around the mouse pointer.",
         "**Molette** : zoom avant et arrière autour du pointeur."),
        ("**Drag** with the left mouse button: move the drawing.",
         "**Glisser** avec le bouton gauche : déplacer le dessin."),
        ("**Double-click**: fit the whole path into the view again (also Tools > Fit Top View).",
         "**Double-clic** : recadrer toute la trajectoire (aussi Tools > Fit Top View)."),
        ("The **grid** shows 10 mm squares; when you zoom out it becomes coarser and the label at the bottom "
         "right tells you the current size.",
         "La **grille** montre des carrés de 10 mm ; lorsque vous dézoomez elle devient plus large et "
         "l'indication en bas à droite donne sa taille actuelle."),
        ("**Purple** lines are the transitions between turns and layers; the **green** dot is the start, "
         "the **red** dot the end. The colour bar shows the layer colours used in the 3D view.",
         "Les lignes **violettes** sont les transitions entre tours et couches ; le point **vert** est le "
         "départ, le point **rouge** la fin. La barre de couleurs montre les couleurs de couches de la "
         "vue 3D."))
h2("Information chips", "Pastilles d'information")
fig("chips.png", 15.0, "The information chips.", "Les pastilles d'information.")
table([3.6, 12.9], [("Chip", "Pastille"), ("Meaning", "Signification")],
      [("moves", "moves"), ("Number of robot moves in the program.", "Nombre de mouvements robot du programme.")],
      [("path", "path"), ("Total length of the path, in metres. Useful to estimate the fiber needed and the "
                          "print time (length ÷ speed).",
                          "Longueur totale de la trajectoire, en mètres. Utile pour estimer la fibre "
                          "nécessaire et la durée (longueur ÷ vitesse).")],
      [("X … Y … Z …", "X … Y … Z …"), ("Smallest and largest X, Y and Z of the path: compare them with the "
                                        "bed and the robot's working area.",
                                        "Plus petites et plus grandes valeurs X, Y et Z : à comparer avec le "
                                        "plateau et la zone de travail du robot.")],
      [("A vs travel", "A vs travel"), ("Largest difference between the head direction A and the real "
                                        "travel direction. With auto-orient it should be 0° to 1°.",
                                        "Plus grand écart entre la direction de la tête A et la direction "
                                        "réelle du déplacement. Avec l'auto-orientation il doit être de 0° "
                                        "à 1°.")],
      [("as exported", "as exported"), ("The number of decimals used for the coordinates (from the export "
                                        "profile).",
                                        "Le nombre de décimales des coordonnées (selon le profil d'export).")])
h2("3D view", "Vue 3D")
p("Click **3D View** (or Ctrl+Shift+D) to open the path in a separate window. It shows exactly what is in "
  "the KRL program box, including your hand edits.",
  "Cliquez sur **3D View** (ou Ctrl+Maj+D) pour ouvrir la trajectoire dans une fenêtre séparée. Elle "
  "montre exactement le contenu de la zone KRL program, y compris vos modifications manuelles.")
fig("view3d.png", 15.5, "The 3D view of a 6-layer cuboid with the head-direction arrows.",
    "La vue 3D d'un pavé de 6 couches avec les flèches de direction de la tête.")
table([4.4, 12.1], [("Control", "Commande"), ("What it does", "Rôle")],
      [("Z exaggeration", "Z exaggeration"), ("Stretches the height (1 to 40 ×) so that thin layers can be "
                                              "told apart. It does not change the program.",
                                              "Étire la hauteur (1 à 40 ×) pour distinguer des couches "
                                              "fines. Ne modifie pas le programme.")],
      [("Colour by layer", "Colour by layer"), ("Each layer gets its own colour (blue at the bottom to orange "
                                                "at the top).",
                                                "Chaque couche a sa couleur (du bleu en bas à l'orange en "
                                                "haut).")],
      [("Head direction (A)", "Head direction (A)"),
       ("Draws an arrow where the head points: **green** = within 5° of the travel direction, **orange** = "
        "5° to 20°, **red** = more than 20°. Red arrows mean the roller would be dragged sideways.",
        "Dessine une flèche dans la direction de la tête : **vert** = à moins de 5° de la direction de "
        "déplacement, **orange** = de 5° à 20°, **rouge** = plus de 20°. Une flèche rouge signifie que le "
        "rouleau serait traîné de côté.")],
      [("Iso / Top / Front / Side", "Iso / Top / Front / Side"), ("Standard viewing directions.",
                                                                  "Directions de vue standard.")],
      [("Reload", "Reload"), ("Reads the program box again after a new Generate or a hand edit.",
                              "Relit la zone de programme après un nouveau Generate ou une modification.")],
      [("Mouse", "Souris"), ("Left-drag: rotate. Right-drag: move. Wheel: zoom. Double-click: reset the view.",
                             "Glisser gauche : rotation. Glisser droit : déplacement. Molette : zoom. "
                             "Double-clic : vue initiale.")])
p("The line at the bottom gives the number of moves, the layers, the Z range, the axis lengths and the "
  "largest head-direction deviation.",
  "La ligne du bas indique le nombre de mouvements, les couches, la plage Z, la longueur des axes et le "
  "plus grand écart de direction de la tête.")

# ----- 9 Program box
h1("The KRL program box", "La zone KRL program")
fig("program_box.png", 15.0, "The KRL program box with its buttons.", "La zone KRL program et ses boutons.")
p("The box shows the robot moves **exactly as they will be exported** (the coordinates are already "
  "rounded to the profile's decimals). The file header with tool, base and speed is added at export and is "
  "not shown here. Keywords are blue, comments grey.",
  "La zone affiche les mouvements du robot **exactement tels qu'ils seront exportés** (les coordonnées "
  "sont déjà arrondies au nombre de décimales du profil). L'en-tête du fichier, avec outil, base et "
  "vitesse, est ajouté à l'export et n'apparaît pas ici. Les mots-clés sont en bleu, les commentaires en "
  "gris.")
h2("Reading the program", "Lire le programme")
bullets(("**; ===== LAYER n =====** starts a layer and tells you whether it spirals outward or inward.",
         "**; ===== LAYER n =====** commence une couche et indique si elle va vers l'extérieur ou "
         "l'intérieur."),
        ("**; L0 T1** marks the first layer (L0), second turn (T1): the program counts from 0. "
         "**TRANSITION** lines mark the purple moves.",
         "**; L0 T1** repère la première couche (L0), deuxième tour (T1) : le programme compte à partir de 0. "
         "Les lignes **TRANSITION** repèrent les mouvements violets."),
        ("**PTP** is the first move to the start point, **LIN** a straight move, **CIRC** an arc through a "
         "middle point to an end point.",
         "**PTP** est le premier mouvement vers le point de départ, **LIN** un mouvement droit, **CIRC** un "
         "arc passant par un point intermédiaire jusqu'à un point final."))
h2("Editing by hand", "Modifier à la main")
p("You can type in the box like in a text editor. Whatever is in the box is exported. **Ctrl+Z / Ctrl+Y** "
  "while the cursor is in the box undo and redo your typing.",
  "Vous pouvez écrire dans la zone comme dans un éditeur de texte. Tout ce qu'elle contient est exporté. "
  "**Ctrl+Z / Ctrl+Y**, quand le curseur est dans la zone, annulent et rétablissent votre saisie.")
note("important",
     "Generate replaces the whole box. Make your hand edits last, after the path is final, and save the "
     "project to keep them.",
     "Generate remplace toute la zone. Faites vos modifications manuelles en dernier, une fois la "
     "trajectoire définitive, et enregistrez le projet pour les conserver.")
h2("Add Comment", "Add Comment (ajouter un commentaire)")
fig("add_comment.png", 9.0, "Adding a comment.", "Ajout d'un commentaire.")
p("Click in the box on the line **above which** the comment should go, then click **Add Comment...**, type "
  "the text and click **Add**. It is inserted as a **;** comment line. The robot ignores comments; they help the operator (for example "
  "\"check tension here\").",
  "Cliquez dans la zone sur la ligne **au-dessus de laquelle** le commentaire doit être placé, puis sur "
  "**Add Comment...**, tapez le texte et cliquez sur **Add**. Il est inséré comme ligne de commentaire **;**. Le robot ignore les "
  "commentaires ; ils aident l'opérateur (par exemple « vérifier la tension ici »).")
h2("Add Approach", "Add Approach (ajouter une approche)")
fig("add_approach.png", 8.0, "Adding an approach move above the start point.",
    "Ajout d'un mouvement d'approche au-dessus du point de départ.")
p("An approach move is a **PTP** move to a safe point, typically right above the start point, so the head "
  "comes down vertically onto the bed. Put the text cursor on the first PTP line, click **Add Approach...**, "
  "enter X, Y and a higher Z (A, B and C are pre-filled from the orientation fields) and click **Add**. The "
  "move is inserted above the cursor line.",
  "Un mouvement d'approche est un mouvement **PTP** vers un point sûr, en général juste au-dessus du point "
  "de départ, pour que la tête descende verticalement sur le plateau. Placez le curseur sur la première "
  "ligne PTP, cliquez sur **Add Approach...**, saisissez X, Y et un Z plus haut (A, B et C sont pré-remplis "
  "avec les champs d'orientation) puis cliquez sur **Add**. Le mouvement est inséré au-dessus de la ligne "
  "du curseur.")
note("tip",
     "The start point is the first PTP line of the program. Copy its X and Y into the approach move and add "
     "50 mm or more to its Z.",
     "Le point de départ est la première ligne PTP du programme. Recopiez son X et son Y dans le mouvement "
     "d'approche et ajoutez 50 mm ou plus à son Z.")
h2("Undo, Redo and Clear", "Undo, Redo et Clear")
p("**Undo** and **Redo** (buttons, Edit menu, or Ctrl+Z / Ctrl+Y outside the text box) go back and forward "
  "through the last 20 changes: Generate, Clear, comments, approach moves and opened projects, together with "
  "the input values. **Clear** empties the program box (it can be undone).",
  "**Undo** et **Redo** (boutons, menu Edit, ou Ctrl+Z / Ctrl+Y hors de la zone de texte) reviennent en "
  "arrière et en avant sur les 20 dernières modifications : Generate, Clear, commentaires, approches et "
  "projets ouverts, avec les valeurs saisies. **Clear** vide la zone de programme (annulable).")

# ----- 10 Export
h1("Exporting the program to the robot", "Exporter le programme vers le robot")
steps(("Click **Export KRL...** (or File > Export KRL Code, or Ctrl+E).",
       "Cliquez sur **Export KRL...** (ou File > Export KRL Code, ou Ctrl+E)."),
      ("Choose the folder (a USB stick, for example) and type a file name. Keep the type **KRL program "
       "(*.src)**; **Text file (*.txt)** writes the same content for reading or e-mail.",
       "Choisissez le dossier (par exemple une clé USB) et tapez un nom de fichier. Gardez le type **KRL "
       "program (*.src)** ; **Text file (*.txt)** écrit le même contenu pour lecture ou envoi par e-mail."),
      ("Click **Save**. A message confirms which export profile was used.",
       "Cliquez sur **Save**. Un message confirme le profil d'export utilisé."))
h2("File name rules", "Règles pour le nom de fichier")
p("The file name becomes the program name on the robot, so the controller's naming rules apply:",
  "Le nom du fichier devient le nom du programme sur le robot ; les règles de nommage de la baie "
  "s'appliquent donc :")
bullets(("Only letters, digits and the underscore **_**. No spaces, no dashes, no accents.",
         "Uniquement des lettres, des chiffres et le tiret bas **_**. Pas d'espace, pas de tiret, pas "
         "d'accent."),
        ("It must not start with a digit, and it can have at most 24 characters.",
         "Il ne doit pas commencer par un chiffre et compte au maximum 24 caractères."),
        ("Good: **Wall_150x300_L3**, **Tube_D120**. Refused: **Wall 150x300**, **3_layers**, **tube-01**.",
         "Corrects : **Wall_150x300_L3**, **Tube_D120**. Refusés : **Wall 150x300**, **3_layers**, "
         "**tube-01**."))
h2("What is in the exported file", "Contenu du fichier exporté")
p("The program writes a complete KUKA program: the standard header, the line **; Export profile: <name>**, "
  "the tool, base, blending, speed and acceleration of the active profile, the first move to HOME, then "
  "your moves (with C_DIS when the option is on), and **END**.",
  "Le programme écrit un programme KUKA complet : l'en-tête standard, la ligne **; Export profile: <nom>**, "
  "l'outil, la base, l'approximation, la vitesse et l'accélération du profil actif, le premier mouvement "
  "vers HOME, puis vos mouvements (avec C_DIS si l'option est active), et **END**.")
code("; ===== LAYER 0 ===== (OUTWARD SPIRAL)\n"
     "; L0 T0 - START\n"
     "PTP {X 587.5, Y 160.0, Z 65.0, A 180.0, B 0.0, C 180.0, S 2., T 43.}\n"
     "CIRC {X 466.59, Y 153.41, Z 65.0},{X 460.0, Y 137.5, Z 65.0, A -90.0, B 0.0, C 180.0} C_DIS\n"
     "LIN {X 460.0, Y -117.5, Z 65.0, A -90.0, B 0.0, C 180.0} C_DIS")
h2("On the robot", "Sur le robot")
steps(("Plug the USB stick into the controller (or the smartPAD) and copy the .src file into your program "
       "folder with the file manager (expert user level may be needed).",
       "Branchez la clé USB sur la baie (ou le smartPAD) et copiez le fichier .src dans votre dossier de "
       "programmes avec le gestionnaire de fichiers (le niveau utilisateur expert peut être nécessaire)."),
      ("Select the program and run the dry run described in chapter 16 before the real print.",
       "Sélectionnez le programme et effectuez l'essai à vide décrit au chapitre 16 avant la vraie "
       "impression."))
note("important",
     "The exported file sets TOOL_DATA and BASE_DATA from the export profile. Running it overwrites those "
     "tool and base numbers on the controller. Check the profile (chapter 11) before you export.",
     "Le fichier exporté définit TOOL_DATA et BASE_DATA à partir du profil d'export. Son exécution remplace "
     "ces numéros d'outil et de base sur la baie. Vérifiez le profil (chapitre 11) avant d'exporter.")

# ----- 11 Export settings
h1("Export settings (profiles)", "Réglages d'export (profils)")
p("An export profile is a named set of robot settings that is written into the header of every exported "
  "program. Open it with **Tools > Export Settings**. The badge at the top right of the main window always "
  "shows which profile is active.",
  "Un profil d'export est un ensemble nommé de réglages robot écrit dans l'en-tête de chaque programme "
  "exporté. Ouvrez-le avec **Tools > Export Settings**. Le badge en haut à droite de la fenêtre principale "
  "indique toujours le profil actif.")
fig("export_settings.png", 13.5, "The Export Settings window (profile NouvTete).",
    "La fenêtre Export Settings (profil NouvTete).")
table([4.0, 12.5], [("Section", "Section"), ("Content", "Contenu")],
      [("Profile", "Profile"), ("Choose the profile to view or edit. \"(active: used for export)\" marks the "
                                "one used by Export.",
                                "Choisit le profil à afficher ou modifier. « (active: used for export) » "
                                "repère celui utilisé à l'export.")],
      [("TOOL", "TOOL"), ("Tool number and the TCP of the print head (X, Y, Z in mm, A, B, C in degrees).",
                          "Numéro d'outil et TCP de la tête d'impression (X, Y, Z en mm, A, B, C en degrés).")],
      [("BASE", "BASE"), ("Base number and the position of the print bed.",
                          "Numéro de base et position du plateau d'impression.")],
      [("Motion", "Motion"),
       ("$APO.CDIS: blending distance for C_DIS (mm). $APO.CPTP: PTP blending (%). VEL_PTP: PTP speed (%). "
        "**VEL_CP: path speed in m/s.** ACC_CP / ACC_AXIS: accelerations (%).",
        "$APO.CDIS : distance d'approximation pour C_DIS (mm). $APO.CPTP : approximation PTP (%). VEL_PTP : "
        "vitesse PTP (%). **VEL_CP : vitesse de trajectoire en m/s.** ACC_CP / ACC_AXIS : accélérations (%).")],
      [("Output", "Output"), ("Coordinate decimals (0 to 6; empty = full precision). 3 is recommended.",
                              "Décimales des coordonnées (0 à 6 ; vide = précision complète). 3 est "
                              "recommandé.")],
      [("Header comments", "Header comments"), ("Notes written as comments into the header (for example where "
                                                "the TCP value comes from).",
                                                "Notes écrites en commentaires dans l'en-tête (par exemple "
                                                "l'origine de la valeur du TCP).")])
h2("Buttons", "Boutons")
bullets(("**Save (use for export)**: stores the changes and makes this profile the active one.",
         "**Save (use for export)** : enregistre les modifications et rend ce profil actif."),
        ("**Save as New...**: stores the values under a new name, for example for another head or bed.",
         "**Save as New...** : enregistre les valeurs sous un nouveau nom, par exemple pour une autre tête "
         "ou un autre plateau."),
        ("**Delete**: removes the selected profile (the last remaining profile cannot be deleted).",
         "**Delete** : supprime le profil sélectionné (le dernier profil restant ne peut pas être supprimé)."),
        ("**Close**: closes the window without saving.", "**Close** : ferme la fenêtre sans enregistrer."))
p("The profiles are stored in **export_profiles.json** next to the program, so every PC that has the same "
  "file exports the same header. If you change the number of decimals, the program box is updated at once "
  "(unless you edited it by hand).",
  "Les profils sont enregistrés dans **export_profiles.json** à côté du programme : tous les PC qui ont le "
  "même fichier exportent le même en-tête. Si vous changez le nombre de décimales, la zone de programme est "
  "mise à jour immédiatement (sauf si vous l'avez modifiée à la main).")
note("safety",
     "VEL_CP is in metres per second: 2 means 2 m/s, which is far too fast for printing (about 0.01 m/s is "
     "intended). Until this value is set for printing, control the speed with the override on the smartPAD "
     "and start low.",
     "VEL_CP est en mètres par seconde : 2 signifie 2 m/s, ce qui est beaucoup trop rapide pour imprimer "
     "(environ 0,01 m/s est visé). Tant que cette valeur n'est pas réglée pour l'impression, contrôlez la "
     "vitesse avec l'override du smartPAD et commencez bas.")
note("important",
     "Change TOOL and BASE only with measured values. A wrong TCP moves the whole print in space.",
     "Ne modifiez TOOL et BASE qu'avec des valeurs mesurées. Un TCP faux déplace toute l'impression dans "
     "l'espace.")

# ----- 12 Projects
h1("Projects: saving and reopening a print", "Projets : enregistrer et rouvrir une impression")
p("A project file (**.json**) keeps everything needed to repeat a print: the shape, all input values, the "
  "options and the program box (including your comments and hand edits), plus a copy of the export profile "
  "that was active.",
  "Un fichier projet (**.json**) conserve tout ce qu'il faut pour reproduire une impression : la forme, "
  "toutes les valeurs saisies, les options et la zone de programme (y compris vos commentaires et "
  "modifications), ainsi qu'une copie du profil d'export actif.")
bullets(("**File > Save Project...** (Ctrl+Shift+S) saves it. The window title then shows the project name.",
         "**File > Save Project...** (Ctrl+Maj+S) l'enregistre. Le titre de la fenêtre affiche alors le nom "
         "du projet."),
        ("**File > Open Project...** (Ctrl+Shift+O) restores everything. Opening can be undone with Undo.",
         "**File > Open Project...** (Ctrl+Maj+O) restaure tout. L'ouverture peut être annulée avec Undo."))
h2("Messages when opening", "Messages à l'ouverture")
table([5.5, 11.0], [("Message", "Message"), ("Meaning", "Signification")],
      [("The saved output differs from what this version generates",
        "The saved output differs from what this version generates"),
       ("The program box was edited by hand, or the program has changed since. The SAVED text is kept. Press "
        "Generate only if you want a fresh path from the inputs.",
        "La zone de programme a été modifiée à la main, ou le programme a évolué depuis. Le texte "
        "ENREGISTRÉ est conservé. N'appuyez sur Generate que si vous voulez une trajectoire recalculée.")],
      [("Profile warning", "Avertissement de profil"),
       ("The project was exported with other settings than the active profile. The active profile is used "
        "for the next export; check it.",
        "Le projet a été exporté avec d'autres réglages que le profil actif. Le profil actif sera utilisé au "
        "prochain export ; vérifiez-le.")],
      [("Old projects", "Anciens projets"),
       ("Projects of the earlier cuboid and cylinder programs open too. The title says \"from the … app\"; "
        "Save Project writes the new format (the old file is not changed). A cuboid whose base was made "
        "point by point is offered to the manual editor (chapter 14).",
        "Les projets des anciens programmes pavé et cylindre s'ouvrent aussi. Le titre indique « from the … "
        "app » ; Save Project écrit le nouveau format (l'ancien fichier n'est pas modifié). Un pavé dont la "
        "base a été faite point par point est proposé à l'éditeur manuel (chapitre 14).")])
note("tip",
     "Save a project for every real print, with the same name as the .src file. Then you always know which "
     "settings produced which part.",
     "Enregistrez un projet pour chaque impression réelle, avec le même nom que le fichier .src. Vous "
     "saurez toujours quels réglages ont produit quelle pièce.")

# ----- 13 Theme
h1("Light and dark theme", "Thème clair et sombre")
p("The **Theme** menu switches between **Light** and **Dark**. The choice is remembered for the next start "
  "and also applies to an open 3D view.",
  "Le menu **Theme** bascule entre **Light** (clair) et **Dark** (sombre). Le choix est conservé au "
  "prochain démarrage et s'applique aussi à une vue 3D ouverte.")
fig("main_dark.png", 15.0, "The dark theme.", "Le thème sombre.")


h1("Advanced tools", "Outils avancés")
h2("Manual 11-point editor", "Éditeur manuel à 11 points")
p("**Tools > Manual 11-point editor (advanced)** opens the earlier cuboid program. Use it only when a base "
  "loop cannot be described by a rounded rectangle: you build the first loop point by point (or import "
  "it), then let it generate the turns and layers.",
  "**Tools > Manual 11-point editor (advanced)** ouvre l'ancien programme de pavé. Ne l'utilisez que si la "
  "boucle de base ne peut pas être décrite par un rectangle arrondi : vous construisez la première boucle "
  "point par point (ou l'importez), puis il génère les tours et couches.")
fig("manual_editor.png", 14.0, "The manual 11-point editor.", "L'éditeur manuel à 11 points.")
steps(("Build the base loop: enter X, Y, Z, A, B, C and click **Add Point** (use **CIRC** for the corner "
       "arcs), or use **Functions > Auto-Generate Base**, or **Import Points** from a saved points file.",
       "Construisez la boucle de base : saisissez X, Y, Z, A, B, C et cliquez sur **Add Point** (utilisez "
       "**CIRC** pour les arcs de coin), ou utilisez **Functions > Auto-Generate Base**, ou **Import Points** "
       "depuis un fichier de points enregistré."),
      ("Enter **Turn Step E**, **Layer Height W**, the number of turns and layers, and the tilt angle.",
       "Saisissez **Turn Step E**, **Layer Height W**, le nombre de tours et de couches et l'angle "
       "d'inclinaison."),
      ("Click **Automate**: the turns and layers appear in the text box and on the canvas.",
       "Cliquez sur **Automate** : les tours et couches apparaissent dans la zone de texte et sur le dessin."),
      ("Click **Export KRL Code**. The same export profile as in the main window is used.",
       "Cliquez sur **Export KRL Code**. Le même profil d'export que dans la fenêtre principale est "
       "utilisé."),
      ("Close the window (or **Back**) to return to the main window.",
       "Fermez la fenêtre (ou **Back**) pour revenir à la fenêtre principale."))
note("important",
     "In the manual editor, the numbers of turns and layers are counted differently: entering N gives N + 1 "
     "turns and N + 1 layers. Its B/tilt is limited to 5 to 20°.",
     "Dans l'éditeur manuel, le nombre de tours et de couches est compté différemment : saisir N donne "
     "N + 1 tours et N + 1 couches. Son B/inclinaison est limité de 5 à 20°.")
h2("Free-form editor (experimental)", "Éditeur libre (expérimental)")
p("**Tools > Free-form editor (experimental)** builds a path from single LIN, CIRC and SPLINE moves. It is "
  "a test tool: it writes its own header with different tool and base values. Do not use its programs "
  "on the robot without checking the header.",
  "**Tools > Free-form editor (experimental)** construit une trajectoire à partir de mouvements LIN, CIRC "
  "et SPLINE individuels. C'est un outil d'essai : il écrit son propre en-tête avec d'autres valeurs "
  "d'outil et de base. N'utilisez pas ses programmes sur le robot sans vérifier l'en-tête.")

h1("Keyboard and mouse", "Clavier et souris")
table([5.0, 11.5], [("Keys", "Touches"), ("Action", "Action")],
      [("Ctrl+G", "Ctrl+G"), ("Generate", "Generate (générer)")],
      [("Ctrl+E", "Ctrl+E"), ("Export KRL code", "Exporter le code KRL")],
      [("Ctrl+Shift+D", "Ctrl+Maj+D"), ("3D View", "Vue 3D")],
      [("Ctrl+Shift+O", "Ctrl+Maj+O"), ("Open Project", "Ouvrir un projet")],
      [("Ctrl+Shift+S", "Ctrl+Maj+S"), ("Save Project", "Enregistrer le projet")],
      [("Ctrl+Z / Ctrl+Y", "Ctrl+Z / Ctrl+Y"),
       ("Undo / Redo. Inside the program box: undo / redo your typing.",
        "Annuler / Rétablir. Dans la zone de programme : annuler / rétablir la saisie.")],
      [("Wheel / drag / double-click", "Molette / glisser / double-clic"),
       ("Top view: zoom / move / fit.", "Vue de dessus : zoom / déplacement / recadrage.")],
      [("Left / right drag, wheel", "Glisser gauche / droit, molette"),
       ("3D view: rotate / move / zoom; double-click resets.",
        "Vue 3D : rotation / déplacement / zoom ; double-clic pour réinitialiser.")])
p("**Help** in the menu bar repeats the main points: **How to use**, **Current shape** and **Keyboard and "
  "mouse**.",
  "Le menu **Help** rappelle l'essentiel : **How to use**, **Current shape** et **Keyboard and mouse**.")

h1("Safety and first run on the robot", "Sécurité et premier essai sur le robot")
p("The program calculates the path, but it does not know the real cell. Follow these steps for every new "
  "program and after every change of tool, base or size.",
  "Le programme calcule la trajectoire, mais il ne connaît pas la cellule réelle. Suivez ces étapes pour "
  "chaque nouveau programme et après chaque changement d'outil, de base ou de dimensions.")
steps(("Check in the program: the X/Y/Z ranges fit the bed, the A vs travel chip is close to 0°, the 3D "
       "view shows no red arrows.",
       "Vérifiez dans le programme : les plages X/Y/Z tiennent sur le plateau, la pastille A vs travel est "
       "proche de 0°, la vue 3D ne montre aucune flèche rouge."),
      ("Check the export profile (badge): correct TOOL and BASE numbers and values.",
       "Vérifiez le profil d'export (badge) : numéros et valeurs TOOL et BASE corrects."),
      ("On the robot, select **T1**, set a low override (for example 10 %) and run without fiber and "
       "resin.",
       "Sur le robot, sélectionnez **T1**, réglez un override faible (par exemple 10 %) et exécutez sans "
       "fibre ni résine."),
      ("Stop at the first point (the PTP start) and check the head height above the bed and the head "
       "direction.",
       "Arrêtez-vous au premier point (le départ PTP) et vérifiez la hauteur de la tête au-dessus du "
       "plateau et sa direction."),
      ("Run one full layer dry, watching the corners, the transitions and the cables and tubes of the "
       "head.",
       "Exécutez une couche complète à vide en surveillant les coins, les transitions ainsi que les câbles "
       "et tuyaux de la tête."),
      ("Only then print with fiber, resin and UV, increasing the override step by step.",
       "Seulement ensuite, imprimez avec fibre, résine et UV en augmentant l'override progressivement."))
note("safety",
     "Keep the enabling switch and the emergency stop within reach. Never stand inside the cell in "
     "automatic mode.",
     "Gardez l'interrupteur d'assentiment et l'arrêt d'urgence à portée de main. Ne restez jamais dans la "
     "cellule en mode automatique.")

h1("Troubleshooting", "Dépannage")
table([5.6, 10.9], [("Problem", "Problème"), ("What to do", "Que faire")],
      [("\"Input Error: Please enter numbers…\"", "« Input Error: Please enter numbers… »"),
       ("A field is empty or contains text. Use a dot as the decimal separator (2.5, not 2,5). Only Corner "
        "radius may be blank.",
        "Un champ est vide ou contient du texte. Utilisez le point comme séparateur décimal (2.5 et non "
        "2,5). Seul Corner radius peut rester vide.")],
      [("\"Turns and layers must be whole numbers\"", "« Turns and layers must be whole numbers »"),
       ("Enter 1, 2, 3 … in Turns per layer and Layers.", "Saisissez 1, 2, 3 … dans Turns per layer et "
                                                          "Layers.")],
      [("\"Corner radius must be … at most half the shorter side\"",
        "« Corner radius must be … at most half the shorter side »"),
       ("Make the radius smaller or leave it blank.", "Réduisez le rayon ou laissez le champ vide.")],
      [("\"The helix option needs exactly 1 turn\"", "« The helix option needs exactly 1 turn »"),
       ("Set Turns per layer to 1 or untick Helix.", "Réglez Turns per layer sur 1 ou décochez Helix.")],
      [("\"Inner diameter too small for this ring step E\"",
        "« Inner diameter too small for this ring step E »"),
       ("Increase the inner diameter or reduce E.", "Augmentez le diamètre intérieur ou réduisez E.")],
      [("Warning \"… below 20 mm: the head may not follow it well\"",
        "Avertissement « … below 20 mm: the head may not follow it well »"),
       ("The path was generated, but a curve is tight. Prefer larger radii or diameters.",
        "La trajectoire est générée, mais une courbe est serrée. Préférez des rayons ou diamètres plus "
        "grands.")],
      [("\"… is not a valid KRL program name\"", "« … is not a valid KRL program name »"),
       ("Rename the file (letters, digits, _; no leading digit; max. 24 characters). Nothing was saved.",
        "Renommez le fichier (lettres, chiffres, _ ; pas de chiffre au début ; 24 caractères max.). Rien "
        "n'a été enregistré.")],
      [("\"Nothing to export yet\"", "« Nothing to export yet »"),
       ("Click Generate first.", "Cliquez d'abord sur Generate.")],
      [("Export Settings warning at export", "Avertissement Export Settings à l'export"),
       ("export_profiles.json is missing or damaged; the built-in profile was used. Put the correct file "
        "next to the program.",
        "export_profiles.json manque ou est endommagé ; le profil intégré a été utilisé. Placez le bon "
        "fichier à côté du programme.")],
      [("Red arrows in the 3D view", "Flèches rouges dans la vue 3D"),
       ("Auto-orient is off, or the program was edited by hand. Tick auto-orient and Generate again.",
        "L'auto-orientation est désactivée ou le programme a été modifié à la main. Cochez "
        "l'auto-orientation et relancez Generate.")],
      [("The robot stops at every point", "Le robot s'arrête à chaque point"),
       ("Check that C_DIS was ticked at export and that the robot runs in continuous mode, not single "
        "step.",
        "Vérifiez que C_DIS était coché à l'export et que le robot est en marche continue et non en pas "
        "à pas.")],
      [("Windows blocks the program at start", "Windows bloque le programme au démarrage"),
       ("Click More info > Run anyway (chapter 2). An antivirus may scan it the first time; the next starts "
        "are faster.",
        "Cliquez sur Informations complémentaires > Exécuter quand même (chapitre 2). Un antivirus peut "
        "l'analyser la première fois ; les démarrages suivants sont plus rapides.")],
      [("The window looks wrong on another PC", "La fenêtre s'affiche mal sur un autre PC"),
       ("Run KRL_Generator.exe --debug-ui in the program folder and send the file debug_ui.txt to the "
        "program's maintainer.",
        "Lancez KRL_Generator.exe --debug-ui dans le dossier du programme et envoyez le fichier "
        "debug_ui.txt au responsable du programme.")])

# ----- Appendix
h1("Appendix: default values and glossary", "Annexe : valeurs par défaut et glossaire")
h2("Default values", "Valeurs par défaut")
table([6.0, 4.0, 6.5], [("Field", "Champ"), ("Default", "Défaut"), ("Note", "Remarque")],
      [("Centre X / Centre Y", "Centre X / Centre Y"), ("535 / 10 mm", "535 / 10 mm"), ("", "")],
      [("Start Z", "Start Z"), ("65 mm", "65 mm"), ("", "")],
      [("Length X × Width Y (cuboid)", "Length X × Width Y (pavé)"), ("150 × 300 mm", "150 × 300 mm"),
       ("Corner radius blank = 22.5 mm", "Corner radius vide = 22,5 mm")],
      [("Inner diameter (cylinder)", "Inner diameter (cylindre)"), ("100 mm", "100 mm"), ("", "")],
      [("Turn step E / Layer height", "Turn step E / Layer height"), ("2 / 2 mm", "2 / 2 mm"), ("", "")],
      [("Turns per layer / Layers", "Turns per layer / Layers"), ("3 / 3", "3 / 3"), ("Exact counts",
                                                                                     "Valeurs exactes")],
      [("A / B / C", "A / B / C"), ("180 / 0 / 180°", "180 / 0 / 180°"), ("", "")],
      [("Auto-orient, C_DIS", "Auto-orient, C_DIS"), ("On", "Activés"), ("", "")],
      [("Export profile", "Profil d'export"), ("NouvTete", "NouvTete"),
       ("TOOL 3, BASE 1, 3 decimals", "TOOL 3, BASE 1, 3 décimales")])
h2("Glossary", "Glossaire")
table([4.0, 12.5], [("Term", "Terme"), ("Meaning", "Signification")],
      [("KRL / .src", "KRL / .src"), ("KUKA Robot Language; a .src file is a robot program.",
                                      "KUKA Robot Language ; un fichier .src est un programme robot.")],
      [("PTP", "PTP"), ("Point-to-point move: fastest way, the path in between is not controlled.",
                        "Mouvement point à point : le plus rapide, le chemin intermédiaire n'est pas "
                        "contrôlé.")],
      [("LIN", "LIN"), ("Straight-line move.", "Mouvement en ligne droite.")],
      [("CIRC", "CIRC"), ("Arc move through an auxiliary point to an end point.",
                          "Mouvement circulaire passant par un point auxiliaire jusqu'à un point final.")],
      [("C_DIS", "C_DIS"), ("Approximation: the robot blends into the next move instead of stopping.",
                            "Approximation : le robot enchaîne le mouvement suivant au lieu de s'arrêter.")],
      [("TCP / TOOL", "TCP / TOOL"), ("Tool centre point: the point of the head that follows the path.",
                                      "Point central de l'outil : le point de la tête qui suit la trajectoire.")],
      [("BASE", "BASE"), ("The coordinate system of the print bed.", "Le repère du plateau d'impression.")],
      [("Override", "Override"), ("Speed percentage set on the smartPAD.",
                                  "Pourcentage de vitesse réglé au smartPAD.")],
      [("Turn", "Tour"), ("One closed loop of the wall in one layer.",
                          "Une boucle fermée de la paroi dans une couche.")],
      [("Layer", "Couche"), ("All turns at one height.", "Tous les tours à une même hauteur.")],
      [("Transition / seam", "Transition / jonction"),
       ("The short arcs that join turns and layers (purple in the views).",
        "Les arcs courts qui relient tours et couches (en violet dans les vues).")],
      [("Project", "Projet"), ("A .json file with all inputs and the program, to repeat a print.",
                               "Un fichier .json contenant toutes les saisies et le programme, pour "
                               "reproduire une impression.")])

# Cross references above use chapter numbers: keep them in sync with this order.
EXPECTED_CHAPTERS = {
    "Quick start: your first program": 3, "Choosing and sizing the shape": 5, "Export settings (profiles)": 11,
    "Advanced tools": 14, "Safety and first run on the robot": 16, "Installation and start": 2,
}

# ---------------------------------------------------------------------------- rendering

TEXTS = {
    "en": dict(title="KRL Generator", subtitle="User Manual",
               tagline="Offline path generation for continuous-fiber printing\non the KUKA KR 6 R900 sixx",
               version="Version 1.0  ·  November 2026", contents="Contents",
               header="KRL Generator  ·  User Manual", page="Page", of="of", figure="Figure",
               audience="For lab users and supervisors. No programming knowledge is needed.",
               toc_hint="Right-click and choose Update Field if the table of contents is empty."),
    "fr": dict(title="KRL Generator", subtitle="Manuel d'utilisation",
               tagline="Génération hors ligne de trajectoires pour l'impression à fibre continue\n"
                       "sur le KUKA KR 6 R900 sixx",
               version="Version 1.0  ·  novembre 2026", contents="Sommaire",
               header="KRL Generator  ·  Manuel d'utilisation", page="Page", of="sur", figure="Figure",
               audience="Pour les utilisateurs du laboratoire et les encadrants. Aucune connaissance en "
                        "programmation n'est nécessaire.",
               toc_hint="Clic droit puis Mettre à jour les champs si le sommaire est vide."),
}


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear")
    sh.set(qn("w:color"), "auto")
    sh.set(qn("w:fill"), fill)
    tcPr.append(sh)


def cell_borders(cell, **edges):
    """edges: top/left/bottom/right = (size_eighths, colour) or None for no border."""
    tcPr = cell._tc.get_or_add_tcPr()
    b = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        e = OxmlElement("w:" + edge)
        v = edges.get(edge)
        if v is None:
            e.set(qn("w:val"), "nil")
        else:
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), str(v[0]))
            e.set(qn("w:color"), v[1])
        b.append(e)
    tcPr.append(b)


def cell_margins(cell, top=80, bottom=80, left=120, right=120):
    tcPr = cell._tc.get_or_add_tcPr()
    m = OxmlElement("w:tcMar")
    for k, v in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        e = OxmlElement("w:" + k)
        e.set(qn("w:w"), str(v))
        e.set(qn("w:type"), "dxa")
        m.append(e)
    tcPr.append(m)


def para_shade(par, fill):
    pPr = par._p.get_or_add_pPr()
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear")
    sh.set(qn("w:color"), "auto")
    sh.set(qn("w:fill"), fill)
    pPr.append(sh)


def para_border_bottom(par, colour="2563EB", size=12):
    pPr = par._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    e = OxmlElement("w:bottom")
    e.set(qn("w:val"), "single")
    e.set(qn("w:sz"), str(size))
    e.set(qn("w:space"), "4")
    e.set(qn("w:color"), colour)
    bdr.append(e)
    pPr.append(bdr)


def field(par, instr, placeholder=""):
    """Complex field (PAGE, NUMPAGES, TOC ...) in a paragraph."""
    def fc(t):
        r = OxmlElement("w:r")
        f = OxmlElement("w:fldChar")
        f.set(qn("w:fldCharType"), t)
        r.append(f)
        return r
    par._p.append(fc("begin"))
    r = OxmlElement("w:r")
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = " %s " % instr
    r.append(it)
    par._p.append(r)
    par._p.append(fc("separate"))
    if placeholder:
        run = par.add_run(placeholder)
        par._p.append(run._r)
    par._p.append(fc("end"))


LANG = ["en"]


def typo(text):
    """French typography: non-breaking space before : ; ? ! and inside « », so they never wrap."""
    if LANG[0] != "fr":
        return text
    text = re.sub(r" ([:;?!»])", " \\1", text)
    return text.replace("« ", "« ")


def add_rich(par, text, size=None, color=None, font=None, bold_color=None):
    """Text with **bold** parts."""
    text = typo(text)
    for i, part in enumerate(re.split(r"\*\*", text)):
        if not part:
            continue
        r = par.add_run(part)
        if i % 2:
            r.bold = True
            if bold_color is not None:
                r.font.color.rgb = bold_color
        if size:
            r.font.size = Pt(size)
        if color is not None and not (i % 2 and bold_color is not None):
            r.font.color.rgb = color
        if font:
            r.font.name = font
    return par


def keep_next(par):
    par.paragraph_format.keep_with_next = True


def set_cell_text(cell, text, bold=False, color=None, size=9.5, align=None):
    cell.text = ""
    par = cell.paragraphs[0]
    par.paragraph_format.space_after = Pt(0)
    par.paragraph_format.space_before = Pt(0)
    if align:
        par.alignment = align
    add_rich(par, "**%s**" % text if bold else text, size=size, color=color)
    return par


def table_width(tbl, widths):
    tbl.autofit = False
    for row in tbl.rows:
        for c, w in zip(row.cells, widths):
            c.width = Cm(w)
    # fixed layout so Word keeps the widths
    tblPr = tbl._tbl.tblPr
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblPr.append(lay)


def repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    e = OxmlElement("w:tblHeader")
    e.set(qn("w:val"), "true")
    trPr.append(e)


def cant_split(row):
    trPr = row._tr.get_or_add_trPr()
    e = OxmlElement("w:cantSplit")
    e.set(qn("w:val"), "true")
    trPr.append(e)


def setup_styles(doc):
    st = doc.styles
    normal = st["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.12
    for name, size, before, after, color in (("Heading 1", 17, 6, 10, NAVY), ("Heading 2", 12.5, 14, 4, ACCENT)):
        s = st[name]
        s.font.name = HEAD_FONT
        s.element.rPr.rFonts.set(qn("w:ascii"), HEAD_FONT)
        s.element.rPr.rFonts.set(qn("w:hAnsi"), HEAD_FONT)
        s.font.size = Pt(size)
        s.font.bold = False
        s.font.color.rgb = color
        s.paragraph_format.space_before = Pt(before)
        s.paragraph_format.space_after = Pt(after)
        s.paragraph_format.keep_with_next = True
    # Word's built-in contents styles are named "toc 1" / "toc 2" (lower case); Word uses them
    # when it refreshes the contents, so they must carry the look.
    for name in ("toc 1", "toc 2"):
        try:
            s = st[name]
        except KeyError:
            from docx.enum.style import WD_STYLE_TYPE
            s = st.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            s.base_style = st["Normal"]
        # make it Word's built-in style (id TOC1/TOC2, not custom), else Word replaces it on update
        s.element.set(qn("w:styleId"), "TOC" + name[-1])
        s.element.attrib.pop(qn("w:customStyle"), None)
        s.font.name = BODY_FONT
        s.paragraph_format.line_spacing = 1.0
        if name == "toc 1":
            s.font.size = Pt(10.5)
            s.font.bold = True
            s.font.color.rgb = NAVY
            s.paragraph_format.space_before = Pt(3)
            s.paragraph_format.space_after = Pt(0)
        else:
            s.font.size = Pt(10)
            s.paragraph_format.left_indent = Cm(0.8)
            s.paragraph_format.space_before = Pt(0)
            s.paragraph_format.space_after = Pt(0)


def header_footer(section, T):
    section.different_first_page_header_footer = True
    hp = section.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = hp.add_run(T["header"])
    r.font.size = Pt(8.5)
    r.font.color.rgb = GREY
    para_border_bottom(hp, "D0D7E2", 6)
    fp = section.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for txt, instr in ((T["page"] + " ", "PAGE"), (" " + T["of"] + " ", "NUMPAGES")):
        r = fp.add_run(txt)
        r.font.size = Pt(8.5)
        r.font.color.rgb = GREY
        field(fp, instr, "1")
    for r in fp.runs:
        r.font.size = Pt(8.5)
        r.font.color.rgb = GREY


def cover(doc, T):
    for _ in range(3):
        doc.add_paragraph()
    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.LEFT
    par.add_run().add_picture(os.path.join(FIG, "icon", "KRL_Generator_icon_256.png"), width=Cm(3.2))
    par = doc.add_paragraph()
    par.paragraph_format.space_before = Pt(18)
    par.paragraph_format.space_after = Pt(0)
    r = par.add_run(T["title"])
    r.font.name = HEAD_FONT
    r.font.size = Pt(36)
    r.font.color.rgb = NAVY
    par = doc.add_paragraph()
    par.paragraph_format.space_after = Pt(14)
    r = par.add_run(T["subtitle"])
    r.font.name = "Segoe UI Light"
    r.font.size = Pt(24)
    r.font.color.rgb = ACCENT
    para_border_bottom(par, "2563EB", 18)
    for line in T["tagline"].split("\n"):
        par = doc.add_paragraph()
        par.paragraph_format.space_after = Pt(0)
        r = par.add_run(line)
        r.font.size = Pt(13)
        r.font.color.rgb = GREY
    for _ in range(2):
        doc.add_paragraph()
    par = doc.add_paragraph()
    par.add_run().add_picture(os.path.join(FIG, "main_light.png"), width=Cm(12.5))
    for _ in range(1):
        doc.add_paragraph()
    par = doc.add_paragraph()
    par.paragraph_format.space_after = Pt(2)
    r = par.add_run(T["version"])
    r.font.size = Pt(10)
    r.font.color.rgb = NAVY
    r.bold = True
    par = doc.add_paragraph()
    r = par.add_run(T["audience"])
    r.font.size = Pt(10)
    r.font.color.rgb = GREY


def toc(doc, T):
    par = doc.add_paragraph()
    par.paragraph_format.page_break_before = True
    r = par.add_run(T["contents"])
    r.font.name = HEAD_FONT
    r.font.size = Pt(20)
    r.font.color.rgb = NAVY
    para_border_bottom(par, "2563EB", 12)
    # A real TOC field, pre-filled with the headings (no page numbers yet): Word fills in the page
    # numbers when the document is opened (updateFields in settings.xml) or with F9.
    entries = toc_entries(T)
    pages = toc_pages(len(entries))
    pars = []
    for level, text in entries:
        par = doc.add_paragraph(style="toc %d" % level)
        par.paragraph_format.tab_stops.add_tab_stop(Cm(16.6), alignment=2, leader=1)  # right, dots
        pars.append((par, text))

    def fc(t):
        r = OxmlElement("w:r")
        f = OxmlElement("w:fldChar")
        f.set(qn("w:fldCharType"), t)
        r.append(f)
        return r
    first = pars[0][0]._p
    first.append(fc("begin"))
    r = OxmlElement("w:r")
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = ' TOC \\o "1-2" \\h \\z \\u '
    r.append(it)
    first.append(r)
    first.append(fc("separate"))
    for k, (par, text) in enumerate(pars):
        par.add_run(text + ("	%d" % pages[k] if pages else ""))
    pars[-1][0]._p.append(fc("end"))
    return bool(pages)


def toc_entries(T):
    """(level, 'n   title') for every heading, numbered exactly like build() does."""
    i = 0 if LANG[0] == "en" else 1
    out, ch, sub = [], 0, 0
    for item in C:
        if item[0] == "h1":
            ch, sub = ch + 1, 0
            out.append((1, "%d   %s" % (ch, typo(item[1 + i]))))
        elif item[0] == "h2":
            sub += 1
            out.append((2, "%d.%d   %s" % (ch, sub, typo(item[1 + i]))))
    return out


def toc_pages(n):
    """Page numbers of the headings from toc_pages.json (written by toc_pages.py from a Word-made
    PDF of the same document), or None if missing / out of date (then Word fills them in)."""
    import json
    try:
        with open(os.path.join(HERE, "toc_pages.json"), encoding="utf-8") as f:
            pages = json.load(f).get(LANG[0])
    except (OSError, ValueError):
        return None
    return pages if isinstance(pages, list) and len(pages) == n else None


def update_fields_on_open(doc):
    """Ask Word to refresh all fields (contents page numbers, page count) when the file opens."""
    settings = doc.settings.element
    e = OxmlElement("w:updateFields")
    e.set(qn("w:val"), "true")
    settings.append(e)


def note_box(doc, kind, text, lang):
    fill, bar, len_, lfr = NOTE_STYLES[kind]
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.rows[0].cells[0]
    shade(cell, fill)
    cell_borders(cell, left=(24, bar))
    cell_margins(cell, 100, 100, 180, 160)
    table_width(tbl, [16.5])
    cant_split(tbl.rows[0])
    par = cell.paragraphs[0]
    par.paragraph_format.space_after = Pt(0)
    r = par.add_run((len_ if lang == "en" else lfr) + "   ")
    r.bold = True
    r.font.color.rgb = RGBColor.from_string(bar)
    r.font.size = Pt(10)
    add_rich(par, text, size=10)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def data_table(doc, widths, header, rows, lang):
    i = 0 if lang == "en" else 1
    tbl = doc.add_table(rows=1 + len(rows), cols=len(widths))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    for c, h in enumerate(header):
        cell = tbl.rows[0].cells[c]
        shade(cell, "1E3A5F")
        set_cell_text(cell, h[i], bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
    repeat_header(tbl.rows[0])
    for ri, row in enumerate(rows, 1):
        cant_split(tbl.rows[ri])
        for c, val in enumerate(row):
            cell = tbl.rows[ri].cells[c]
            if ri % 2 == 0:
                shade(cell, "F3F6FA")
            set_cell_text(cell, val[i], bold=(c == 0 and len(widths) > 1))
    for row in tbl.rows:
        for cell in row.cells:
            cell_borders(cell, top=None, left=None, right=None, bottom=(4, "D0D7E2"))
            cell_margins(cell, 60, 60, 100, 100)
    table_width(tbl, widths)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def code_block(doc, text):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.rows[0].cells[0]
    shade(cell, "F3F4F6")
    cell_borders(cell, left=(12, "9CA3AF"))
    cell_margins(cell, 80, 80, 160, 120)
    table_width(tbl, [16.5])
    cell.text = ""
    for k, line in enumerate(text.split("\n")):
        par = cell.paragraphs[0] if k == 0 else cell.add_paragraph()
        par.paragraph_format.space_after = Pt(0)
        par.paragraph_format.line_spacing = 1.0
        r = par.add_run(line)
        r.font.name = "Consolas"
        r.font.size = Pt(8)
        r.font.color.rgb = GREY if line.startswith(";") else RGBColor(0x11, 0x18, 0x27)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def build(lang):
    LANG[0] = lang
    T = {k: typo(v) for k, v in TEXTS[lang].items()}
    i = 0 if lang == "en" else 1
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(2.0)
    sec.header_distance = sec.footer_distance = Cm(1.0)
    setup_styles(doc)
    header_footer(sec, T)
    cover(doc, T)
    has_pages = toc(doc, T)

    ch, sub, fign, steps_n = 0, 0, 0, 0
    chapters = {}
    for item in C:
        kind = item[0]
        if kind == "h1":
            ch += 1
            sub = 0
            chapters[item[1]] = ch
            par = doc.add_heading("%d   %s" % (ch, typo(item[1 + i])), level=1)
            par.paragraph_format.page_break_before = True
            para_border_bottom(par, "2563EB", 12)
        elif kind == "h2":
            sub += 1
            doc.add_heading("%d.%d   %s" % (ch, sub, typo(item[1 + i])), level=2)
        elif kind == "p":
            add_rich(doc.add_paragraph(), item[1 + i])
        elif kind in ("bullets", "steps"):
            for n, it in enumerate(item[1], 1):
                text = it[i]
                indent = text.startswith("    ")
                par = doc.add_paragraph(style="List Number" if kind == "steps" else "List Bullet"
                                        if not indent else "List Bullet 2")
                par.paragraph_format.space_after = Pt(3)
                if kind == "steps":
                    # restart numbering per list: write the numbers ourselves instead
                    par.style = doc.styles["Normal"]
                    par.paragraph_format.left_indent = Cm(0.9)
                    par.paragraph_format.first_line_indent = Cm(-0.9)
                    par.paragraph_format.tab_stops.add_tab_stop(Cm(0.9))
                    r = par.add_run("%d\t" % n)
                    r.bold = True
                    r.font.color.rgb = ACCENT
                add_rich(par, text.strip())
            doc.paragraphs[-1].paragraph_format.space_after = Pt(8)
        elif kind == "fig":
            _, name, width, en, fr = item
            fname = name[i] if isinstance(name, tuple) else name
            fign += 1
            par = doc.add_paragraph()
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            par.paragraph_format.space_before = Pt(4)
            par.paragraph_format.space_after = Pt(2)
            keep_next(par)
            par.add_run().add_picture(os.path.join(FIG, fname), width=Cm(width))
            cap = doc.add_paragraph()
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap.paragraph_format.space_after = Pt(10)
            r = cap.add_run("%s %d.  " % (T["figure"], fign))
            r.bold = True
            r.font.size = Pt(9)
            r.font.color.rgb = NAVY
            r = cap.add_run(typo(en if lang == "en" else fr))
            r.italic = True
            r.font.size = Pt(9)
            r.font.color.rgb = GREY
        elif kind == "note":
            note_box(doc, item[1], item[2 + i], lang)
        elif kind == "table":
            data_table(doc, item[1], item[2], item[3], lang)
        elif kind == "code":
            code_block(doc, item[1])
        elif kind == "pagebreak":
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    if lang == "en":
        for title, n in EXPECTED_CHAPTERS.items():
            assert chapters.get(title) == n, "chapter '%s' is %s, text refers to %d" % (title, chapters.get(title), n)
    if not has_pages:
        update_fields_on_open(doc)
    out = os.path.join(HERE, "KRL_Generator_User_Manual_%s.docx" % lang.upper())
    doc.save(out)
    print("wrote", out, "-", ch, "chapters,", fign, "figures")
    return chapters


if __name__ == "__main__":
    chap = build("en")
    print({k: v for k, v in chap.items()})
    build("fr")
