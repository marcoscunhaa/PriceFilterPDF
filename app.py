import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
from pathlib import Path
from collections import defaultdict
from array import array
import random

import pdfplumber


# ============================================================
# CONFIGURAÇÃO
# ============================================================

COL_WIDTHS = {
    0: 120,  # Código
    1: 500,  # Descrição
    2: 110,  # Preço UN.
    3: 80,   # Qtd.
    4: 120,  # NCM
    5: 120,  # Copiar código
    6: 70,   # Cópias
}

# Limite de segurança para o calculador avançado.
# R$ 20.000,00 = 2.000.000 centavos
MAX_COMBINATION_CENTS = 2_000_000

# Quantas tentativas serão feitas para procurar
# combinações diferentes.
RANDOM_ATTEMPTS = 20

# Limite visual da descrição.
# Evita que descrições gigantes destruam a tabela.
DESCRIPTION_MAX_CHARS = 58

# ============================================================
# IDENTIDADE VISUAL — MIX MODA
# ============================================================

MIX_YELLOW = "#F4C400"
MIX_YELLOW_LIGHT = "#FFF8D8"
MIX_RED = "#C62828"
MIX_RED_DARK = "#9E1F1F"
MIX_DARK = "#242424"
MIX_TEXT = "#2B2B2B"
MIX_MUTED = "#6F6F6F"
MIX_BG = "#FAFAF7"
MIX_WHITE = "#FFFFFF"

# Intervalo curto usado para a entrada suave das linhas após uma busca.
SEARCH_ANIMATION_DELAY_MS = 8
SEARCH_ANIMATION_BATCH = 12


# ============================================================
# EXPRESSÕES
# ============================================================

MONEY_RE = r"[\d.]+,\d{2}"

NCM_RE = r"\d{4}\.\d{2}\.\d{2}"

CODE_RE = re.compile(
    r"^\d{4,}$"
)


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalize_money(value: str) -> str:

    value = (
        str(value)
        .strip()
        .upper()
        .replace("R$", "")
        .replace(" ", "")
    )

    if not value:
        return ""

    if "," in value:
        value = value.replace(".", "")
        value = value.replace(",", ".")

    return value


def br_money(value) -> str:

    try:

        number = float(
            normalize_money(value)
        )

        return (
            f"{number:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    except Exception:

        return str(value)


def format_quantity(value) -> str:

    try:

        number = float(value)

        if number.is_integer():
            return str(int(number))

        return (
            f"{number:.2f}"
            .replace(".", ",")
        )

    except Exception:

        return str(value)


def parse_number(value):

    try:

        return float(
            normalize_money(value)
        )

    except Exception:

        return None


def money_to_cents(value):

    try:

        number = float(
            normalize_money(value)
        )

        return int(
            round(number * 100)
        )

    except Exception:

        return None


# ============================================================
# LIMPEZA DE TEXTO
# ============================================================

def clean_text(value) -> str:

    if value is None:
        return ""

    value = str(value)

    value = value.replace(
        "\n",
        " "
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def truncate_text(
    text,
    max_chars=DESCRIPTION_MAX_CHARS
):

    text = clean_text(text)

    if len(text) <= max_chars:
        return text

    return (
        text[:max_chars - 3]
        + "..."
    )


# ============================================================
# CABEÇALHOS / RUÍDO
# ============================================================

HEADER_WORDS = (
    "código",
    "codigo",
    "descrição",
    "descricao",
    "grupo mercadoria",
    "custo un.",
    "custo un",
    "preço un.",
    "preço un",
    "preco un.",
    "preco un",
    "ncm",
    "registros:",
)


def is_noise(line: str) -> bool:

    line = clean_text(line)

    if not line:
        return True

    low = line.lower()

    return any(
        word in low
        for word in HEADER_WORDS
    )


# ============================================================
# PARSER
# ============================================================

def parse_product_line(
    line,
    page_number=0
):

    line = clean_text(line)

    if not line:
        return None

    code_match = re.match(
        r"^(\d{4,})\s+(.+)$",
        line
    )

    if not code_match:
        return None

    code = code_match.group(1)

    remaining = (
        code_match.group(2).strip()
    )

    pattern = re.compile(
        rf"^(?P<desc>.*?)\s+"
        rf"(?P<unit>[A-Za-zÀ-ÿ]+)\s+"
        rf"(?P<cost>{MONEY_RE})\s+"
        rf"(?P<price>{MONEY_RE})\s+"
        rf"(?P<minimum>{MONEY_RE})\s+"
        rf"(?P<quantity>[\d.]+(?:,\d+)?)\s+"
        rf"(?P<ncm>{NCM_RE})\s+"
        rf"(?P<total_cost>{MONEY_RE})\s+"
        rf"(?P<total_price>{MONEY_RE})$",
        re.IGNORECASE
    )

    match = pattern.match(
        remaining
    )

    if not match:
        return None

    data = match.groupdict()

    quantity = parse_number(
        data["quantity"]
    )

    if quantity is None:
        return None

    return {
        "code": code,
        "description": clean_text(
            data["desc"]
        ),
        "unit": data["unit"],
        "cost": data["cost"],
        "price": data["price"],
        "minimum": data["minimum"],
        "quantity": quantity,
        "ncm": data["ncm"],
        "total_cost": data["total_cost"],
        "total_price": data["total_price"],
        "page": page_number,
    }


# ============================================================
# LEITURA POR TABELA
# ============================================================

def extract_products_from_tables(
    pdf_path: str
):

    products = []

    with pdfplumber.open(pdf_path) as pdf:

        for page_number, page in enumerate(
            pdf.pages,
            start=1
        ):

            try:

                tables = page.extract_tables()

            except Exception:

                tables = []

            for table in tables:

                if not table:
                    continue

                for row in table:

                    if not row:
                        continue

                    cells = [
                        clean_text(cell)
                        for cell in row
                    ]

                    cells = [
                        cell
                        for cell in cells
                        if cell
                    ]

                    if not cells:
                        continue

                    # --------------------------------------------
                    # TABELA NORMAL
                    # --------------------------------------------

                    if len(cells) >= 10:

                        code = cells[0]

                        if not CODE_RE.match(
                            code
                        ):
                            continue

                        description = cells[1]
                        unit = cells[2]
                        cost = cells[3]
                        price = cells[4]
                        minimum = cells[5]
                        quantity = cells[6]
                        ncm = cells[7]
                        total_cost = cells[8]
                        total_price = cells[9]

                        if not re.fullmatch(
                            MONEY_RE,
                            cost
                        ):
                            continue

                        if not re.fullmatch(
                            MONEY_RE,
                            price
                        ):
                            continue

                        if not re.fullmatch(
                            NCM_RE,
                            ncm
                        ):
                            continue

                        quantity_number = parse_number(
                            quantity
                        )

                        if quantity_number is None:
                            continue

                        products.append(
                            {
                                "code": code,
                                "description": description,
                                "unit": unit,
                                "cost": cost,
                                "price": price,
                                "minimum": minimum,
                                "quantity": quantity_number,
                                "ncm": ncm,
                                "total_cost": total_cost,
                                "total_price": total_price,
                                "page": page_number,
                            }
                        )

                        continue

                    # --------------------------------------------
                    # TUDO EM UMA CÉLULA
                    # --------------------------------------------

                    joined = " ".join(
                        cells
                    )

                    product = parse_product_line(
                        joined,
                        page_number
                    )

                    if product:
                        products.append(
                            product
                        )

    return products


# ============================================================
# LEITURA POR TEXTO
# ============================================================

def extract_products_from_text(
    pdf_path: str
):

    products = []

    with pdfplumber.open(pdf_path) as pdf:

        for page_number, page in enumerate(
            pdf.pages,
            start=1
        ):

            text = page.extract_text(
                x_tolerance=2,
                y_tolerance=3
            ) or ""

            raw_lines = text.splitlines()

            lines = [
                clean_text(line)
                for line in raw_lines
            ]

            pending = None

            for line in lines:

                if not line:
                    continue

                if is_noise(line):
                    continue

                # --------------------------------------------
                # NOVO PRODUTO
                # --------------------------------------------

                if re.match(
                    r"^\d{4,}\s+",
                    line
                ):

                    if pending:

                        product = parse_product_line(
                            pending,
                            page_number
                        )

                        if product:
                            products.append(
                                product
                            )

                    pending = line

                # --------------------------------------------
                # CONTINUAÇÃO
                # --------------------------------------------

                elif pending:

                    pending += (
                        " " + line
                    )

            # --------------------------------------------
            # ÚLTIMO PRODUTO
            # --------------------------------------------

            if pending:

                product = parse_product_line(
                    pending,
                    page_number
                )

                if product:
                    products.append(
                        product
                    )

    return products


# ============================================================
# LEITOR PRINCIPAL
# ============================================================

def extract_products(pdf_path: str):

    table_products = []
    text_products = []

    try:

        table_products = (
            extract_products_from_tables(
                pdf_path
            )
        )

    except Exception:

        table_products = []

    try:

        text_products = (
            extract_products_from_text(
                pdf_path
            )
        )

    except Exception:

        text_products = []

    all_products = (
        table_products +
        text_products
    )

    unique = {}

    for product in all_products:

        code = product.get(
            "code",
            ""
        )

        if not code:
            continue

        existing = unique.get(
            code
        )

        if existing is None:

            unique[code] = product

        else:

            fields = (
                "description",
                "price",
                "quantity",
                "ncm",
            )

            existing_score = sum(
                bool(existing.get(field))
                for field in fields
            )

            new_score = sum(
                bool(product.get(field))
                for field in fields
            )

            if new_score > existing_score:

                unique[code] = product

    return list(
        unique.values()
    )


# ============================================================
# APLICAÇÃO
# ============================================================


class RoundedButton(tk.Canvas):
    """Botão visual Mix Moda com cantos arredondados, hover e sombra suave."""

    def __init__(self, master, text="", command=None, style=None, **kwargs):
        self._text = text
        self._command = command
        self._disabled = False
        self._font = kwargs.pop("font", ("Segoe UI", 9, "bold"))
        self._padx = kwargs.pop("padx", 14)
        self._height = kwargs.pop("height", 34)
        self._radius = kwargs.pop("radius", 10)
        self._bg = MIX_RED if style == "Red.TButton" else MIX_YELLOW
        self._fg = MIX_WHITE if style == "Red.TButton" else MIX_DARK
        self._hover_bg = MIX_RED_DARK if style == "Red.TButton" else "#FFD83D"
        self._disabled_bg = "#E5E5E5"
        self._disabled_fg = "#999999"
        self._shadow = "#D8D6D0"
        self._hover = False

        self._font_obj = tk.font.Font(font=self._font)
        text_w = self._font_obj.measure(self._text)
        self._width = max(72, text_w + self._padx * 2)

        super().__init__(
            master,
            width=self._width,
            height=self._height,
            bg=MIX_BG,
            highlightthickness=0,
            bd=0,
            relief="flat",
            cursor="hand2",
            **kwargs
        )
        self.configure(takefocus=True)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Return>", self._on_click)
        self.bind("<space>", self._on_click)
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def _rounded_rect(self, x1, y1, x2, y2, r, fill, outline=None):
        """Desenha um rounded rectangle real usando arcos nativos do Tk.

        Evita o polígono com smooth=True, que gera ondulações/artefatos
        visuais nas curvas e dá aparência de pixel art em alguns tamanhos.
        """
        x1, y1, x2, y2 = map(float, (x1, y1, x2, y2))
        r = max(1, min(float(r), (x2 - x1) / 2, (y2 - y1) / 2))
        fill = fill or ""
        outline = outline or fill
        diameter = 2 * r

        # Corpo central e faixas laterais.
        self.create_rectangle(
            x1 + r, y1, x2 - r, y2,
            fill=fill, outline=outline, width=0
        )
        self.create_rectangle(
            x1, y1 + r, x2, y2 - r,
            fill=fill, outline=outline, width=0
        )

        # Quatro quartos de círculo nativos: curvas limpas e simétricas.
        boxes = [
            (x1, y1, x1 + diameter, y1 + diameter, 90),
            (x2 - diameter, y1, x2, y1 + diameter, 0),
            (x2 - diameter, y2 - diameter, x2, y2, 270),
            (x1, y2 - diameter, x1 + diameter, y2, 180),
        ]
        for bx1, by1, bx2, by2, start in boxes:
            self.create_arc(
                bx1, by1, bx2, by2,
                start=start, extent=90,
                fill=fill, outline=outline, width=0
            )

    def _draw(self):
        self.delete("all")
        w = max(self.winfo_width(), self._width)
        h = max(self.winfo_height(), self._height)

        # Mantém uma margem real ao redor do botão para a sombra não
        # cortar os cantos. A sombra é composta pelo mesmo rounded rect,
        # garantindo que o contorno fique uniforme.
        shadow_x1 = 3
        shadow_y1 = 5
        shadow_x2 = w - 2
        shadow_y2 = h - 1
        shadow_radius = max(4, min(self._radius, (shadow_x2-shadow_x1)/2, (shadow_y2-shadow_y1)/2))
        self._rounded_rect(
            shadow_x1, shadow_y1, shadow_x2, shadow_y2,
            shadow_radius, self._shadow
        )

        bg = self._disabled_bg if self._disabled else (self._hover_bg if self._hover else self._bg)
        fg = self._disabled_fg if self._disabled else self._fg

        button_x1 = 2
        button_y1 = 1
        button_x2 = w - 3
        button_y2 = h - 5
        button_radius = max(4, min(self._radius, (button_x2-button_x1)/2, (button_y2-button_y1)/2))
        self._rounded_rect(
            button_x1, button_y1, button_x2, button_y2,
            button_radius, bg
        )

        self.create_text(
            w / 2, (button_y1 + button_y2) / 2,
            text=self._text, fill=fg,
            font=self._font_obj, anchor="center"
        )

    def _on_enter(self, _event=None):
        if not self._disabled:
            self._hover = True
            self._draw()

    def _on_leave(self, _event=None):
        self._hover = False
        self._draw()

    def _on_click(self, _event=None):
        if not self._disabled and self._command:
            self._command()

    def state(self, states=None):
        """Compatibilidade com ttk.Button.state([...])."""
        if states is None:
            return ["disabled"] if self._disabled else []
        for st in states:
            if st == "disabled":
                self._disabled = True
            elif st == "!disabled":
                self._disabled = False
        self.configure(cursor="arrow" if self._disabled else "hand2")
        self._draw()


class App:

    def __init__(self, root):

        self.root = root

        self.root.title(
            "Consulta de Preço — PDF"
        )

        self.root.geometry(
            "1180x720"
        )

        self.root.minsize(
            1000,
            600
        )

        # ====================================================
        # DADOS
        # ====================================================

        self.products = []

        self.current_results = []

        self.copy_counts = defaultdict(
            int
        )

        self.total_copies = 0

        self.current_pdf = ""

        # ====================================================
        # ORDENAÇÃO
        # ====================================================

        self.sort_column = None

        self.sort_reverse = True

        # ====================================================
        # COMBINAÇÃO AVANÇADA
        # ====================================================

        self.current_combination = []

        self.combination_target = None

        # Controle da animação de renderização. Um novo render
        # invalida qualquer animação anterior.
        self._render_generation = 0
        self._render_after_id = None

        # ====================================================
        # INTERFACE
        # ====================================================

        self.build_ui()


    # ========================================================
    # INTERFACE
    # ========================================================

    def build_ui(self):

        self.root.configure(bg=MIX_BG)

        style = ttk.Style(self.root)

        try:
            style.theme_use("clam")
        except Exception:
            pass

        # ====================================================
        # ESTILO MIX MODA
        # ====================================================

        style.configure(
            ".",
            font=("Segoe UI", 10),
            background=MIX_BG,
            foreground=MIX_TEXT
        )
        style.configure(
            "Mix.TFrame",
            background=MIX_BG
        )
        style.configure(
            "Mix.TLabel",
            background=MIX_BG,
            foreground=MIX_TEXT
        )
        style.configure(
            "Muted.TLabel",
            background=MIX_BG,
            foreground=MIX_MUTED
        )
        style.configure(
            "MixHeader.TLabel",
            background=MIX_DARK,
            foreground=MIX_WHITE,
            font=("Segoe UI", 9, "bold")
        )
        style.configure(
            "MixTitle.TLabel",
            background=MIX_BG,
            foreground=MIX_DARK,
            font=("Segoe UI", 20, "bold")
        )
        style.configure(
            "MixBrand.TLabel",
            background=MIX_YELLOW,
            foreground=MIX_DARK,
            font=("Segoe UI", 12, "bold"),
            padding=(14, 6)
        )
        style.configure(
            "Mix.TButton",
            background=MIX_YELLOW,
            foreground=MIX_DARK,
            borderwidth=0,
            padding=(12, 7),
            font=("Segoe UI", 9, "bold")
        )
        style.map(
            "Mix.TButton",
            background=[("active", "#FFD83D"), ("disabled", "#E2E2E2")],
            foreground=[("disabled", "#999999")]
        )
        style.configure(
            "Red.TButton",
            background=MIX_RED,
            foreground=MIX_WHITE,
            borderwidth=0,
            padding=(12, 7),
            font=("Segoe UI", 9, "bold")
        )
        style.map(
            "Red.TButton",
            background=[("active", MIX_RED_DARK), ("disabled", "#E2E2E2")],
            foreground=[("disabled", "#999999")]
        )
        style.configure(
            "Mix.TEntry",
            fieldbackground=MIX_WHITE,
            foreground=MIX_TEXT,
            bordercolor=MIX_YELLOW,
            lightcolor=MIX_YELLOW,
            darkcolor=MIX_YELLOW,
            padding=7
        )
        style.configure(
            "Mix.TLabelframe",
            background=MIX_BG,
            bordercolor=MIX_YELLOW,
            relief="solid"
        )
        style.configure(
            "Mix.TLabelframe.Label",
            background=MIX_BG,
            foreground=MIX_RED,
            font=("Segoe UI", 10, "bold")
        )
        style.configure(
            "Mix.Horizontal.TSeparator",
            background=MIX_YELLOW
        )

        # ====================================================
        # TOPO
        # ====================================================

        top = ttk.Frame(
            self.root,
            padding=(18, 14, 18, 10),
            style="Mix.TFrame"
        )
        top.pack(fill="x")

        brand_line = tk.Frame(
            top,
            bg=MIX_BG,
            height=42
        )
        brand_line.pack(fill="x", pady=(0, 9))

        # Banner da marca — arredondado, elegante e com texto vermelho.
        brand_banner = tk.Canvas(
            brand_line,
            width=150,
            height=38,
            bg=MIX_BG,
            highlightthickness=0,
            bd=0
        )
        brand_banner.pack(side="left")

        def draw_brand_banner(_event=None):
            brand_banner.delete("all")

            w = max(150, brand_banner.winfo_width())
            h = max(38, brand_banner.winfo_height())
            r = 12
            x1, y1, x2, y2 = 2, 2, w - 2, h - 3

            # Sombra discreta
            brand_banner.create_arc(
                x1, y1 + 3, x1 + 2*r, y1 + 3 + 2*r,
                start=90, extent=90, fill="#D8D6D0", outline=""
            )
            brand_banner.create_arc(
                x2 - 2*r, y1 + 3, x2, y1 + 3 + 2*r,
                start=0, extent=90, fill="#D8D6D0", outline=""
            )
            brand_banner.create_rectangle(
                x1+r, y1+3, x2-r, y2,
                fill="#D8D6D0", outline=""
            )
            brand_banner.create_rectangle(
                x1, y1+r+3, x2, y2-r,
                fill="#D8D6D0", outline=""
            )
            brand_banner.create_arc(
                x1, y1, x1 + 2*r, y1 + 2*r,
                start=90, extent=90, fill=MIX_YELLOW, outline=""
            )
            brand_banner.create_arc(
                x2 - 2*r, y1, x2, y1 + 2*r,
                start=0, extent=90, fill=MIX_YELLOW, outline=""
            )
            brand_banner.create_arc(
                x2 - 2*r, y2 - 2*r, x2, y2,
                start=270, extent=90, fill=MIX_YELLOW, outline=""
            )
            brand_banner.create_arc(
                x1, y2 - 2*r, x1 + 2*r, y2,
                start=180, extent=90, fill=MIX_YELLOW, outline=""
            )
            brand_banner.create_rectangle(
                x1+r, y1, x2-r, y2,
                fill=MIX_YELLOW, outline=""
            )
            brand_banner.create_rectangle(
                x1, y1+r, x2, y2-r,
                fill=MIX_YELLOW, outline=""
            )

            brand_banner.create_text(
                w / 2,
                (y1 + y2) / 2,
                text="MIX MODA",
                fill=MIX_RED,
                font=("Segoe UI", 12, "bold"),
                anchor="center"
            )

        brand_banner.bind("<Configure>", draw_brand_banner)
        brand_banner.after_idle(draw_brand_banner)

        ttk.Label(
            brand_line,
            text="  SITIO SÃO JOÃO • SAPIRANGA • PEDRAS • PALMEIRAS",
            style="Muted.TLabel",
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=10)

        ttk.Label(
            top,
            text="Consulta de Preço",
            style="MixTitle.TLabel"
        ).pack(anchor="w")

        ttk.Label(
            top,
            text=(
                "Selecione o PDF, digite o Preço UN. "
                "e copie o código do produto."
            ),
            style="Muted.TLabel",
            font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(2, 12))

        # ====================================================
        # CONTROLES PRINCIPAIS
        # ====================================================

        controls = ttk.Frame(
            top,
            style="Mix.TFrame"
        )

        controls.pack(
            fill="x"
        )

        RoundedButton(
            controls,
            text="📄 Selecionar PDF",
            command=self.select_pdf,
            style="Mix.TButton"
        ).pack(
            side="left"
        )

        self.file_label = ttk.Label(
            controls,
            text="Nenhum PDF selecionado",
            width=55,
            style="Muted.TLabel"
        )

        self.file_label.pack(
            side="left",
            padx=12
        )

        ttk.Label(
            controls,
            text="Preço UN.:",
            style="Mix.TLabel"
        ).pack(
            side="left",
            padx=(15, 5)
        )

        self.price_var = tk.StringVar()

        self.price_entry = ttk.Entry(
            controls,
            textvariable=self.price_var,
            width=15,
            style="Mix.TEntry"
        )

        self.price_entry.pack(
            side="left"
        )

        self.price_entry.bind(
            "<Return>",
            lambda e: self.search()
        )

        RoundedButton(
            controls,
            text="🔎 Buscar",
            command=self.search,
            style="Red.TButton"
        ).pack(
            side="left",
            padx=6
        )

        RoundedButton(
            controls,
            text="Limpar",
            command=self.clear_search,
            style="Mix.TButton"
        ).pack(
            side="left"
        )

        # ====================================================
        # MODO AVANÇADO
        # ====================================================

        advanced = ttk.LabelFrame(
            top,
            text=" ⚡ Modo Avançado — Montar valor ",
            style="Mix.TLabelframe"
        )

        advanced.pack(
            fill="x",
            pady=(15, 5)
        )

        advanced_top = ttk.Frame(
            advanced,
            padding=8,
            style="Mix.TFrame"
        )

        advanced_top.pack(
            fill="x"
        )

        ttk.Label(
            advanced_top,
            text="Valor desejado:",
            style="Mix.TLabel"
        ).pack(
            side="left"
        )

        self.combination_var = (
            tk.StringVar()
        )

        self.combination_entry = ttk.Entry(
            advanced_top,
            textvariable=self.combination_var,
            width=15,
            style="Mix.TEntry"
        )

        self.combination_entry.pack(
            side="left",
            padx=(6, 6)
        )

        self.combination_entry.bind(
            "<Return>",
            lambda e:
                self.generate_combination()
        )

        RoundedButton(
            advanced_top,
            text="⚡ Montar combinação",
            command=self.generate_combination,
            style="Red.TButton"
        ).pack(
            side="left"
        )

        RoundedButton(
            advanced_top,
            text="🎲 Nova combinação",
            command=self.generate_random_combination,
            style="Mix.TButton"
        ).pack(
            side="left",
            padx=6
        )

        # ----------------------------------------------------
        # REMOVIDO:
        #
        # Botão global "Copiar códigos"
        #
        # Agora cada linha possui seu próprio botão
        # para copiar individualmente.
        # ----------------------------------------------------

        self.combination_status = (
            tk.StringVar(
                value=(
                    "Digite um valor para "
                    "o sistema encontrar uma combinação."
                )
            )
        )

        ttk.Label(
            advanced_top,
            textvariable=self.combination_status,
            style="Muted.TLabel"
        ).pack(
            side="left",
            padx=12
        )

        # ====================================================
        # ÁREA DA COMBINAÇÃO
        # ====================================================

        combination_container = ttk.Frame(
            advanced,
            padding=(8, 0, 8, 8),
            style="Mix.TFrame"
        )

        combination_container.pack(
            fill="x"
        )

        # Frame próprio para as linhas da combinação.
        # Isso permite colocar um botão real em cada linha.
        self.combination_rows_frame = ttk.Frame(
            combination_container,
            style="Mix.TFrame"
        )

        self.combination_rows_frame.pack(
            fill="x"
        )

        # ====================================================
        # STATUS
        # ====================================================

        self.status_var = tk.StringVar(
            value=(
                "Selecione um PDF para começar."
            )
        )

        ttk.Label(
            top,
            textvariable=self.status_var,
            style="Muted.TLabel",
            font=("Segoe UI", 10)
        ).pack(
            anchor="w",
            pady=(10, 0)
        )

        # ====================================================
        # RESUMO
        # ====================================================

        summary = ttk.Frame(
            self.root,
            padding=(15, 0, 15, 8),
            style="Mix.TFrame"
        )

        summary.pack(
            fill="x"
        )

        self.result_var = tk.StringVar(
            value="Resultados: 0"
        )

        self.copy_var = tk.StringVar(
            value="Total de cópias: 0"
        )

        ttk.Label(
            summary,
            textvariable=self.result_var,
            style="Mix.TLabel"
        ).pack(
            side="left"
        )

        ttk.Label(
            summary,
            textvariable=self.copy_var,
            style="Mix.TLabel",
            font=("Segoe UI", 10, "bold")
        ).pack(
            side="right"
        )

        # ====================================================
        # TABELA PRINCIPAL
        # ====================================================

        container = ttk.Frame(
            self.root,
            padding=(15, 0, 15, 15),
            style="Mix.TFrame"
        )

        container.pack(
            fill="both",
            expand=True
        )

        self.canvas = tk.Canvas(
            container,
            highlightthickness=0,
            bg=MIX_WHITE,
            bd=0
        )

        self.scrollbar = ttk.Scrollbar(
            container,
            orient="vertical",
            command=self.canvas.yview
        )

        self.rows_frame = ttk.Frame(
            self.canvas,
            style="Mix.TFrame"
        )

        self.rows_frame.bind(
            "<Configure>",
            lambda e:
                self.canvas.configure(
                    scrollregion=
                    self.canvas.bbox(
                        "all"
                    )
                )
        )

        self.canvas_window = (
            self.canvas.create_window(
                (0, 0),
                window=self.rows_frame,
                anchor="nw"
            )
        )

        self.canvas.configure(
            yscrollcommand=
            self.scrollbar.set
        )

        self.canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        self.scrollbar.pack(
            side="right",
            fill="y"
        )

        self.canvas.bind(
            "<Configure>",
            lambda e:
                self.canvas.itemconfig(
                    self.canvas_window,
                    width=e.width
                )
        )

        self.render_rows(
            []
        )


    # ========================================================
    # COLUNAS
    # ========================================================

    def configure_columns(
        self,
        frame
    ):

        for column, width in (
            COL_WIDTHS.items()
        ):

            frame.grid_columnconfigure(
                column,
                minsize=width,
                weight=0
            )


    # ========================================================
    # TEXTO DA ORDENAÇÃO
    # ========================================================

    def get_sort_text(
        self,
        title,
        column
    ):

        if self.sort_column == column:

            if self.sort_reverse:

                return f"{title} ↓"

            return f"{title} ↑"

        return f"{title} ↕"


    # ========================================================
    # CABEÇALHO
    # ========================================================

    def make_header(self):

        header = ttk.Frame(
            self.rows_frame
        )

        header.pack(
            fill="x",
            pady=(0, 4)
        )

        self.configure_columns(
            header
        )

        ttk.Label(
            header,
            text="Código",
            font=("Segoe UI", 9, "bold"),
            foreground=MIX_DARK,
            background=MIX_YELLOW,
            anchor="w"
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=3
        )

        ttk.Label(
            header,
            text="Descrição",
            font=("Segoe UI", 9, "bold"),
            foreground=MIX_DARK,
            background=MIX_YELLOW,
            anchor="w"
        ).grid(
            row=0,
            column=1,
            sticky="w",
            padx=3
        )

        RoundedButton(
            header,
            text=self.get_sort_text(
                "Preço UN.",
                "price"
            ),
            command=lambda:
                self.sort_products(
                    "price"
                )
        ).grid(
            row=0,
            column=2,
            sticky="w",
            padx=0
        )

        RoundedButton(
            header,
            text=self.get_sort_text(
                "Qtd.",
                "quantity"
            ),
            command=lambda:
                self.sort_products(
                    "quantity"
                )
        ).grid(
            row=0,
            column=3,
            sticky="w",
            padx=0
        )

        ttk.Label(
            header,
            text="NCM",
            font=("Segoe UI", 9, "bold"),
            foreground=MIX_DARK,
            background=MIX_YELLOW,
            anchor="w"
        ).grid(
            row=0,
            column=4,
            sticky="w",
            padx=3
        )

        ttk.Label(
            header,
            text="Copiar código",
            font=("Segoe UI", 9, "bold"),
            foreground=MIX_DARK,
            background=MIX_YELLOW,
            anchor="w"
        ).grid(
            row=0,
            column=5,
            sticky="w",
            padx=3
        )

        ttk.Label(
            header,
            text="Cópias",
            font=("Segoe UI", 9, "bold"),
            foreground=MIX_DARK,
            background=MIX_YELLOW,
            anchor="w"
        ).grid(
            row=0,
            column=6,
            sticky="w",
            padx=3
        )

        ttk.Separator(
            self.rows_frame,
            orient="horizontal",
            style="Mix.Horizontal.TSeparator"
        ).pack(
            fill="x"
        )


    # ========================================================
    # SELECIONAR PDF
    # ========================================================

    def select_pdf(self):

        path = filedialog.askopenfilename(
            title=(
                "Selecione o relatório PDF"
            ),
            filetypes=[
                (
                    "Arquivos PDF",
                    "*.pdf"
                ),
                (
                    "Todos os arquivos",
                    "*.*"
                )
            ]
        )

        if not path:
            return

        self.current_pdf = path

        self.file_label.config(
            text=Path(path).name
        )

        self.status_var.set(
            "Lendo PDF..."
        )

        self.root.update_idletasks()

        try:

            self.products = (
                extract_products(
                    path
                )
            )

            self.current_results = (
                self.products.copy()
            )

            self.copy_counts.clear()

            self.total_copies = 0

            self.copy_var.set(
                "Total de cópias: 0"
            )

            self.price_var.set("")

            self.sort_column = None

            self.sort_reverse = True

            # Limpa combinação anterior.

            self.clear_combination()

            self.render_rows(
                self.current_results
            )

            self.result_var.set(
                f"Resultados: "
                f"{len(self.products)}"
            )

            if self.products:

                self.status_var.set(
                    "PDF carregado: "
                    f"{len(self.products)} "
                    "produtos encontrados."
                )

            else:

                self.status_var.set(
                    "Não consegui identificar "
                    "produtos neste PDF."
                )

                messagebox.showwarning(
                    "PDF não reconhecido",
                    (
                        "O PDF foi aberto, mas "
                        "nenhum produto foi "
                        "identificado."
                    )
                )

        except Exception as exc:

            self.status_var.set(
                "Erro ao ler o PDF."
            )

            messagebox.showerror(
                "Erro",
                (
                    "Não foi possível ler o PDF."
                    f"\n\nDetalhes:\n{exc}"
                )
            )


    # ========================================================
    # BUSCAR PREÇO
    # ========================================================

    def search(self):

        if not self.products:

            messagebox.showinfo(
                "Selecione um PDF",
                (
                    "Primeiro clique em "
                    "'Selecionar PDF'."
                )
            )

            return

        value = normalize_money(
            self.price_var.get()
        )

        if not value:

            self.current_results = (
                self.products.copy()
            )

            self.render_rows(
                self.current_results
            )

            self.result_var.set(
                f"Resultados: "
                f"{len(self.current_results)}"
            )

            self.status_var.set(
                f"Exibindo todos os "
                f"{len(self.products)} "
                f"produtos."
            )

            return

        try:

            target = float(
                value
            )

        except ValueError:

            messagebox.showwarning(
                "Valor inválido",
                (
                    "Digite um preço como "
                    "5,00 ou 26,00."
                )
            )

            return

        results = []

        for product in self.products:

            try:

                price = float(
                    normalize_money(
                        product["price"]
                    )
                )

                if abs(
                    price - target
                ) < 0.00001:

                    results.append(
                        product
                    )

            except (
                ValueError,
                TypeError
            ):

                pass

        self.current_results = (
            results.copy()
        )

        self.render_rows(
            self.current_results
        )

        self.result_var.set(
            f"Resultados: "
            f"{len(self.current_results)}"
        )

        self.status_var.set(
            "Busca por Preço UN. = "
            f"{br_money(value)}"
        )


    # ========================================================
    # LIMPAR BUSCA
    # ========================================================

    def clear_search(self):

        self.price_var.set("")

        self.current_results = (
            self.products.copy()
        )

        self.render_rows(
            self.current_results
        )

        self.result_var.set(
            f"Resultados: "
            f"{len(self.products)}"
        )

        self.status_var.set(
            f"Exibindo todos os "
            f"{len(self.products)} "
            "produtos."
        )


    # ========================================================
    # ORDENAÇÃO
    # ========================================================

    def sort_products(
        self,
        column
    ):

        if not self.current_results:
            return

        if self.sort_column == column:

            self.sort_reverse = (
                not self.sort_reverse
            )

        else:

            self.sort_column = column

            self.sort_reverse = True

        if column == "price":

            self.current_results.sort(
                key=lambda product:
                    float(
                        normalize_money(
                            product["price"]
                        )
                    ),
                reverse=self.sort_reverse
            )

        elif column == "quantity":

            self.current_results.sort(
                key=lambda product:
                    product["quantity"],
                reverse=self.sort_reverse
            )

        self.render_rows(
            self.current_results
        )

        self.result_var.set(
            f"Resultados: "
            f"{len(self.current_results)}"
        )


    # ========================================================
    # RENDERIZAÇÃO
    # ========================================================

    def render_rows(
        self,
        products,
        animate=True
    ):

        # Cancela qualquer animação anterior para evitar que uma
        # busca rápida misture resultados antigos com os novos.
        self._render_generation += 1
        generation = self._render_generation

        if self._render_after_id is not None:
            try:
                self.root.after_cancel(self._render_after_id)
            except Exception:
                pass
            self._render_after_id = None

        for widget in self.rows_frame.winfo_children():
            widget.destroy()

        self.make_header()

        if not products:
            ttk.Label(
                self.rows_frame,
                text="Nenhum produto encontrado para esse preço.",
                style="Muted.TLabel",
                font=("Segoe UI", 11)
            ).pack(pady=30)
            return

        items = list(products)

        # A entrada em pequenos lotes deixa a troca de resultados
        # visualmente suave sem alterar nenhuma regra de negócio.
        if not animate or len(items) <= SEARCH_ANIMATION_BATCH:
            for product in items:
                self.add_product_row(product)
            self.canvas.update_idletasks()
            self.canvas.yview_moveto(0)
            return

        state = {"index": 0}

        def add_batch():
            if generation != self._render_generation:
                return

            start_index = state["index"]
            end_index = min(
                start_index + SEARCH_ANIMATION_BATCH,
                len(items)
            )

            for product in items[start_index:end_index]:
                self.add_product_row(product)

            state["index"] = end_index
            self.canvas.update_idletasks()

            if end_index < len(items):
                self._render_after_id = self.root.after(
                    SEARCH_ANIMATION_DELAY_MS,
                    add_batch
                )
            else:
                self._render_after_id = None
                self.canvas.yview_moveto(0)

        add_batch()


    # ========================================================
    # LINHA DO PRODUTO
    # ========================================================

    def add_product_row(
        self,
        product
    ):

        row = ttk.Frame(
            self.rows_frame,
            style="Mix.TFrame"
        )

        row.pack(
            fill="x",
            pady=4
        )

        self.configure_columns(
            row
        )

        ttk.Label(
            row,
            text=product["code"],
            anchor="w"
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=3
        )

        # ----------------------------------------------------
        # DESCRIÇÃO LIMITADA
        # ----------------------------------------------------

        ttk.Label(
            row,
            text=truncate_text(
                product["description"]
            ),
            anchor="w"
        ).grid(
            row=0,
            column=1,
            sticky="w",
            padx=3
        )

        ttk.Label(
            row,
            text=br_money(
                product["price"]
            ),
            anchor="w"
        ).grid(
            row=0,
            column=2,
            sticky="w",
            padx=3
        )

        quantity_label = ttk.Label(
            row,
            text=format_quantity(
                product["quantity"]
            ),
            anchor="w"
        )

        quantity_label.grid(
            row=0,
            column=3,
            sticky="w",
            padx=3
        )

        ttk.Label(
            row,
            text=product["ncm"],
            anchor="w"
        ).grid(
            row=0,
            column=4,
            sticky="w",
            padx=3
        )

        copy_button = RoundedButton(
            row,
            text="📋 Copiar",
            command=lambda p=product: self.copy_code(p),
            style="Red.TButton"
        )

        copy_button.grid(
            row=0,
            column=5,
            sticky="w",
            padx=3
        )

        count_label = ttk.Label(
            row,
            text=str(
                self.copy_counts[
                    product["code"]
                ]
            ),
            anchor="w"
        )

        count_label.grid(
            row=0,
            column=6,
            sticky="w",
            padx=3
        )

        product[
            "_quantity_label"
        ] = quantity_label

        product[
            "_copy_button"
        ] = copy_button

        product[
            "_count_label"
        ] = count_label

        if product["quantity"] <= 0:

            copy_button.state(
                ["disabled"]
            )

        ttk.Separator(
            self.rows_frame,
            orient="horizontal",
            style="Mix.Horizontal.TSeparator"
        ).pack(
            fill="x"
        )


    # ========================================================
    # FUNÇÃO CENTRAL DE CÓPIA
    # ========================================================

    def copy_product_code(
        self,
        product,
        show_status=True
    ):
        """
        Copia UM código e contabiliza a operação.

        Esta função é usada tanto pelo botão da tabela
        principal quanto pelos botões individuais do
        Modo Avançado.

        Portanto, os dois lugares compartilham:
        - baixa de estoque;
        - contador de cópias;
        - total geral de cópias;
        - atualização visual da tabela.
        """

        if product["quantity"] <= 0:

            return False

        # ----------------------------------------------------
        # Normaliza o código para copiar.
        # ----------------------------------------------------

        try:

            code = str(
                int(
                    product["code"]
                )
            )

        except ValueError:

            code = product["code"].lstrip(
                "0"
            )

            if not code:
                code = "0"

        # ----------------------------------------------------
        # Copia somente UMA vez.
        # ----------------------------------------------------

        self.root.clipboard_clear()

        self.root.clipboard_append(
            code
        )

        self.root.update()

        # ----------------------------------------------------
        # Baixa uma unidade do estoque.
        # ----------------------------------------------------

        product["quantity"] -= 1

        if product["quantity"] < 0:

            product["quantity"] = 0

        # ----------------------------------------------------
        # Contabiliza a cópia.
        # ----------------------------------------------------

        self.copy_counts[
            product["code"]
        ] += 1

        self.total_copies += 1

        # ----------------------------------------------------
        # Atualiza a linha da tabela principal,
        # se ela estiver atualmente renderizada.
        # ----------------------------------------------------

        quantity_label = product.get(
            "_quantity_label"
        )

        if (
            quantity_label
            and
            quantity_label.winfo_exists()
        ):

            quantity_label.config(
                text=format_quantity(
                    product["quantity"]
                )
            )

        count_label = product.get(
            "_count_label"
        )

        if (
            count_label
            and
            count_label.winfo_exists()
        ):

            count_label.config(
                text=str(
                    self.copy_counts[
                        product["code"]
                    ]
                )
            )

        copy_button = product.get(
            "_copy_button"
        )

        if (
            product["quantity"] <= 0
            and
            copy_button
            and
            copy_button.winfo_exists()
        ):

            copy_button.state(
                ["disabled"]
            )

        # ----------------------------------------------------
        # Atualiza o contador geral.
        # ----------------------------------------------------

        self.copy_var.set(
            f"Total de cópias: "
            f"{self.total_copies}"
        )

        if show_status:

            self.status_var.set(
                f"📋 Código {code} copiado. "
                f"Estoque restante: "
                f"{format_quantity(product['quantity'])}"
            )

        return True


    # ========================================================
    # COPIAR CÓDIGO INDIVIDUAL
    # ========================================================

    def copy_code(
        self,
        product
    ):

        self.copy_product_code(
            product,
            show_status=True
        )

        # Atualiza também a combinação caso o produto
        # tenha acabado de ser zerado.
        self.refresh_combination_copy_buttons()


    # ========================================================
    # COMBINAÇÃO — LIMPAR
    # ========================================================

    def clear_combination(self):

        self.current_combination = []

        self.combination_target = None

        self.combination_status.set(
            "Digite um valor para o sistema encontrar uma combinação."
        )

        if hasattr(
            self,
            "combination_rows_frame"
        ):

            self.clear_combination_tree()


    # ========================================================
    # COMBINAÇÃO — GERAR
    # ========================================================

    def generate_combination(self):

        self._generate_combination(
            force_new=False
        )


    # ========================================================
    # COMBINAÇÃO — RANDOM
    # ========================================================

    def generate_random_combination(self):

        self._generate_combination(
            force_new=True
        )


    # ========================================================
    # MOTOR DA COMBINAÇÃO
    # ========================================================

    def _generate_combination(
        self,
        force_new=False
    ):

        if not self.products:

            messagebox.showinfo(
                "Selecione um PDF",
                (
                    "Primeiro carregue o PDF "
                    "do estoque."
                )
            )

            return

        raw_target = (
            self.combination_var.get()
        )

        target_cents = money_to_cents(
            raw_target
        )

        if (
            target_cents is None
            or
            target_cents <= 0
        ):

            messagebox.showwarning(
                "Valor inválido",
                (
                    "Digite um valor válido.\n\n"
                    "Exemplo: 205,00"
                )
            )

            return

        if target_cents > MAX_COMBINATION_CENTS:

            messagebox.showwarning(
                "Valor muito alto",
                (
                    "Para manter o sistema "
                    "rápido, o valor máximo "
                    "para a combinação é "
                    "R$ 20.000,00."
                )
            )

            return

        self.combination_status.set(
            "🔎 Procurando combinação..."
        )

        self.root.update_idletasks()

        previous_signature = (
            self.get_combination_signature()
        )

        combination = None

        attempts = (
            RANDOM_ATTEMPTS
            if force_new
            else 1
        )

        for _ in range(attempts):

            candidate = (
                self.find_combination(
                    target_cents
                )
            )

            if not candidate:
                continue

            signature = (
                tuple(
                    sorted(
                        (
                            item["code"],
                            item["quantity"]
                        )
                        for item in candidate
                    )
                )
            )

            if (
                not force_new
                or
                signature != previous_signature
            ):

                combination = candidate

                break

            # Se só existir uma combinação,
            # aceita a mesma.

            combination = candidate

        if not combination:

            self.current_combination = []

            self.combination_target = (
                target_cents
            )

            self.clear_combination_tree()

            self.combination_status.set(
                "❌ Não encontrei uma combinação exata "
                "com o estoque disponível."
            )

            return

        self.current_combination = (
            combination
        )

        self.combination_target = (
            target_cents
        )

        self.show_combination()


    # ========================================================
    # ALGORITMO DE COMBINAÇÃO
    # ========================================================

    def find_combination(
        self,
        target_cents
    ):

        # ----------------------------------------------------
        # Somente produtos:
        #
        # - com estoque
        # - com preço válido
        # - preço <= valor desejado
        # ----------------------------------------------------

        available = []

        for product in self.products:

            quantity = int(
                product.get(
                    "quantity",
                    0
                )
            )

            price_cents = money_to_cents(
                product.get(
                    "price",
                    ""
                )
            )

            if quantity <= 0:
                continue

            if not price_cents:
                continue

            if price_cents <= 0:
                continue

            if price_cents > target_cents:
                continue

            available.append(
                (
                    product,
                    quantity,
                    price_cents
                )
            )

        if not available:
            return None

        # ----------------------------------------------------
        # Criamos blocos para transformar o problema
        # de quantidade limitada em vários itens.
        #
        # Exemplo:
        #
        # estoque = 13
        #
        # vira:
        #
        # 1 + 2 + 4 + 6
        #
        # permitindo qualquer quantidade de 0 a 13.
        # ----------------------------------------------------

        chunks = []

        for product, quantity, price_cents in available:

            remaining = quantity

            block = 1

            while remaining > 0:

                take = min(
                    block,
                    remaining
                )

                value = (
                    price_cents * take
                )

                if value <= target_cents:

                    chunks.append(
                        (
                            product,
                            take,
                            value
                        )
                    )

                remaining -= take

                block *= 2

        if not chunks:
            return None

        # ----------------------------------------------------
        # Randomiza a ordem.
        #
        # Isso permite encontrar combinações diferentes.
        # ----------------------------------------------------

        random.shuffle(
            chunks
        )

        # ----------------------------------------------------
        # DP:
        #
        # reachable[s] diz se conseguimos formar
        # exatamente o valor s.
        #
        # Usamos array de inteiros para economizar memória.
        # ----------------------------------------------------

        unreachable = -2

        previous_sum = array(
            "i",
            [unreachable]
        ) * (
            target_cents + 1
        )

        previous_item = array(
            "i",
            [unreachable]
        ) * (
            target_cents + 1
        )

        previous_sum[0] = -1

        # ----------------------------------------------------
        # 0/1 knapsack
        # ----------------------------------------------------

        for index, (
            product,
            quantity,
            value
        ) in enumerate(chunks):

            if value > target_cents:
                continue

            for current in range(
                target_cents,
                value - 1,
                -1
            ):

                previous = (
                    current - value
                )

                if (
                    previous_sum[current]
                    ==
                    unreachable
                    and
                    previous_sum[previous]
                    !=
                    unreachable
                ):

                    previous_sum[current] = (
                        previous
                    )

                    previous_item[current] = (
                        index
                    )

            if (
                previous_sum[
                    target_cents
                ]
                !=
                unreachable
            ):

                break

        # ----------------------------------------------------
        # Não encontrou.
        # ----------------------------------------------------

        if (
            previous_sum[
                target_cents
            ]
            ==
            unreachable
        ):

            return None

        # ----------------------------------------------------
        # Reconstrói a combinação.
        # ----------------------------------------------------

        selected = defaultdict(
            int
        )

        current = target_cents

        while current > 0:

            item_index = (
                previous_item[current]
            )

            if item_index < 0:
                return None

            product, quantity, value = (
                chunks[item_index]
            )

            selected[
                product["code"]
            ] += quantity

            current = (
                previous_sum[current]
            )

        # ----------------------------------------------------
        # Transforma em lista.
        # ----------------------------------------------------

        result = []

        products_by_code = {
            product["code"]: product
            for product, _, _
            in available
        }

        for code, quantity in selected.items():

            product = products_by_code.get(
                code
            )

            if not product:
                continue

            price_cents = money_to_cents(
                product["price"]
            )

            result.append(
                {
                    "code": code,
                    "description":
                        product["description"],
                    "price_cents":
                        price_cents,
                    "quantity":
                        quantity,
                    "subtotal_cents":
                        price_cents * quantity,
                    "product":
                        product,
                }
            )

        return result


    # ========================================================
    # ASSINATURA DA COMBINAÇÃO
    # ========================================================

    def get_combination_signature(self):

        return tuple(
            sorted(
                (
                    item["code"],
                    item["quantity"]
                )
                for item in
                self.current_combination
            )
        )


    # ========================================================
    # MOSTRAR COMBINAÇÃO
    # ========================================================

    def show_combination(self):

        self.clear_combination_tree()

        # ----------------------------------------------------
        # Cabeçalho da combinação
        # ----------------------------------------------------

        header = ttk.Frame(
            self.combination_rows_frame,
            style="Mix.TFrame"
        )

        header.pack(
            fill="x",
            pady=(0, 3)
        )

        header.grid_columnconfigure(
            0,
            minsize=100
        )

        header.grid_columnconfigure(
            1,
            minsize=420
        )

        header.grid_columnconfigure(
            2,
            minsize=90
        )

        header.grid_columnconfigure(
            3,
            minsize=70
        )

        header.grid_columnconfigure(
            4,
            minsize=110
        )

        header.grid_columnconfigure(
            5,
            minsize=120
        )

        headings = (
            ("Código", 0),
            ("Produto", 1),
            ("Preço", 2),
            ("Qtd.", 3),
            ("Subtotal", 4),
            ("Copiar", 5),
        )

        for title, column in headings:

            ttk.Label(
                header,
                text=title,
                font=("Segoe UI", 9, "bold"),
                foreground=MIX_DARK,
                background=MIX_YELLOW,
                anchor="w"
            ).grid(
                row=0,
                column=column,
                sticky="w",
                padx=3
            )

        ttk.Separator(
            self.combination_rows_frame,
            orient="horizontal",
            style="Mix.Horizontal.TSeparator"
        ).pack(
            fill="x"
        )

        total = 0
        total_items = 0

        for item in self.current_combination:

            subtotal = (
                item["subtotal_cents"]
            )

            total += subtotal

            total_items += (
                item["quantity"]
            )

            self.add_combination_row(
                item
            )

        self.combination_status.set(
            "✅ Combinação encontrada: "
            f"{br_money(total / 100)}"
            f"  |  {total_items} item(ns)"
            "  |  Clique em 'Copiar' em cada linha."
        )


    # ========================================================
    # LINHA INDIVIDUAL DA COMBINAÇÃO
    # ========================================================

    def add_combination_row(
        self,
        item
    ):

        row = ttk.Frame(
            self.combination_rows_frame,
            style="Mix.TFrame"
        )

        row.pack(
            fill="x",
            pady=2
        )

        columns = {
            0: 100,
            1: 420,
            2: 90,
            3: 70,
            4: 110,
            5: 120,
        }

        for column, width in columns.items():

            row.grid_columnconfigure(
                column,
                minsize=width,
                weight=0
            )

        product = item["product"]

        ttk.Label(
            row,
            text=item["code"],
            anchor="w"
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=3
        )

        ttk.Label(
            row,
            text=truncate_text(
                item["description"],
                58
            ),
            anchor="w"
        ).grid(
            row=0,
            column=1,
            sticky="w",
            padx=3
        )

        ttk.Label(
            row,
            text=br_money(
                item["price_cents"] / 100
            ),
            anchor="w"
        ).grid(
            row=0,
            column=2,
            sticky="w",
            padx=3
        )

        quantity_label = ttk.Label(
            row,
            text=str(
                item["quantity"]
            ),
            anchor="w"
        )

        quantity_label.grid(
            row=0,
            column=3,
            sticky="w",
            padx=3
        )

        ttk.Label(
            row,
            text=br_money(
                item["subtotal_cents"] / 100
            ),
            anchor="w"
        ).grid(
            row=0,
            column=4,
            sticky="w",
            padx=3
        )

        copy_button = RoundedButton(
            row,
            text="📋 Copiar 1",
            command=lambda p=product: self.copy_combination_item(p),
            style="Red.TButton"
        )

        copy_button.grid(
            row=0,
            column=5,
            sticky="w",
            padx=3
        )

        # Guarda referências para atualizar a linha.
        item["_quantity_label"] = (
            quantity_label
        )

        item["_copy_button"] = (
            copy_button
        )

        item["_row_frame"] = row

        # ----------------------------------------------------
        # O botão só fica disponível se ainda houver estoque.
        # ----------------------------------------------------

        if product["quantity"] <= 0:

            copy_button.state(
                ["disabled"]
            )

        ttk.Separator(
            self.combination_rows_frame,
            orient="horizontal",
            style="Mix.Horizontal.TSeparator"
        ).pack(
            fill="x"
        )


    # ========================================================
    # COPIAR ITEM DA COMBINAÇÃO
    # ========================================================

    def copy_combination_item(
        self,
        product
    ):

        success = self.copy_product_code(
            product,
            show_status=False
        )

        if not success:

            self.combination_status.set(
                "⚠️ Esse produto não possui "
                "mais estoque disponível."
            )

            self.refresh_combination_copy_buttons()

            return

        # ----------------------------------------------------
        # Atualiza todas as linhas da combinação que usam
        # esse produto.
        # ----------------------------------------------------

        for item in self.current_combination:

            if (
                item["product"]["code"]
                ==
                product["code"]
            ):

                # Uma unidade foi copiada.
                if item["quantity"] > 0:

                    item["quantity"] -= 1

                item["subtotal_cents"] = (
                    item["price_cents"]
                    *
                    item["quantity"]
                )

                quantity_label = item.get(
                    "_quantity_label"
                )

                if (
                    quantity_label
                    and
                    quantity_label.winfo_exists()
                ):

                    quantity_label.config(
                        text=str(
                            item["quantity"]
                        )
                    )

                button = item.get(
                    "_copy_button"
                )

                if (
                    item["quantity"] <= 0
                    and
                    button
                    and
                    button.winfo_exists()
                ):

                    button.state(
                        ["disabled"]
                    )

        # ----------------------------------------------------
        # Atualiza o status.
        # ----------------------------------------------------

        self.status_var.set(
            f"📋 Código {self.get_copyable_code(product)} "
            "copiado pelo Modo Avançado. "
            f"Estoque restante: "
            f"{format_quantity(product['quantity'])}"
        )

        self.combination_status.set(
            "📋 Código copiado individualmente. "
            f"Total geral de cópias: "
            f"{self.total_copies}"
        )

        # ----------------------------------------------------
        # Atualiza a tabela principal.
        # ----------------------------------------------------

        self.refresh_main_product_row(
            product
        )

        self.refresh_combination_copy_buttons()


    # ========================================================
    # CÓDIGO COPIÁVEL
    # ========================================================

    def get_copyable_code(
        self,
        product
    ):

        try:

            return str(
                int(
                    product["code"]
                )
            )

        except ValueError:

            code = product["code"].lstrip(
                "0"
            )

            return code if code else "0"


    # ========================================================
    # ATUALIZA LINHA PRINCIPAL
    # ========================================================

    def refresh_main_product_row(
        self,
        product
    ):

        quantity_label = product.get(
            "_quantity_label"
        )

        if (
            quantity_label
            and
            quantity_label.winfo_exists()
        ):

            quantity_label.config(
                text=format_quantity(
                    product["quantity"]
                )
            )

        count_label = product.get(
            "_count_label"
        )

        if (
            count_label
            and
            count_label.winfo_exists()
        ):

            count_label.config(
                text=str(
                    self.copy_counts[
                        product["code"]
                    ]
                )
            )

        copy_button = product.get(
            "_copy_button"
        )

        if (
            product["quantity"] <= 0
            and
            copy_button
            and
            copy_button.winfo_exists()
        ):

            copy_button.state(
                ["disabled"]
            )

        elif (
            product["quantity"] > 0
            and
            copy_button
            and
            copy_button.winfo_exists()
        ):

            copy_button.state(
                ["!disabled"]
            )


    # ========================================================
    # ATUALIZA BOTÕES DA COMBINAÇÃO
    # ========================================================

    def refresh_combination_copy_buttons(self):

        for item in self.current_combination:

            product = item["product"]

            button = item.get(
                "_copy_button"
            )

            if (
                not button
                or
                not button.winfo_exists()
            ):
                continue

            if (
                product["quantity"] <= 0
                or
                item["quantity"] <= 0
            ):

                button.state(
                    ["disabled"]
                )

            else:

                button.state(
                    ["!disabled"]
                )


    # ========================================================
    # LIMPA ÁREA DA COMBINAÇÃO
    # ========================================================

    def clear_combination_tree(self):

        if not hasattr(
            self,
            "combination_rows_frame"
        ):
            return

        for widget in (
            self.combination_rows_frame.winfo_children()
        ):

            widget.destroy()


# ============================================================
# MAIN
# ============================================================

def main():

    root = tk.Tk()

    App(root)

    root.mainloop()


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()
