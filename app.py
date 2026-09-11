import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font as tkfont
from pathlib import Path
from collections import defaultdict

import pdfplumber


# ============================================================
# CONFIGURAÇÃO DAS COLUNAS
# ============================================================

# As mesmas larguras são usadas no cabeçalho e nas linhas.
# Isso mantém tudo alinhado.

COL_WIDTHS = {
    0: 120,  # Código
    1: 500,  # Descrição
    2: 110,  # Preço UN.
    3: 80,   # Qtd.
    4: 120,  # NCM
    5: 120,  # Copiar código
    6: 70,   # Cópias
}


# ============================================================
# CONFIGURAÇÃO VISUAL DA DESCRIÇÃO
# ============================================================

# Espaço interno da coluna.
DESCRIPTION_PADDING = 10

# Largura máxima disponível para o texto.
DESCRIPTION_MAX_WIDTH = (
    COL_WIDTHS[1] - DESCRIPTION_PADDING
)


# ============================================================
# EXPRESSÕES AUXILIARES
# ============================================================

MONEY_RE = r"[\d.]+,\d{2}"

NCM_RE = r"\d{4}\.\d{2}\.\d{2}"

CODE_RE = re.compile(
    r"^\d{4,}$"
)


# ============================================================
# NORMALIZAÇÃO DE VALORES
# ============================================================

def normalize_money(value: str) -> str:
    """
    Converte valores brasileiros para formato comparável.

    Exemplos:

        5,00       -> 5.00
        26,00      -> 26.00
        1.170,00   -> 1170.00
    """

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
    """
    Exibe número no padrão brasileiro.
    """

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
    """
    Formata quantidade para exibição.

    1072.0 -> 1072
    5.0    -> 5
    2.5    -> 2,50
    """

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
    """
    Converte número brasileiro para float.
    """

    try:

        return float(
            normalize_money(value)
        )

    except Exception:

        return None


# ============================================================
# LIMITE DA DESCRIÇÃO
# ============================================================

def truncate_description(
    text,
    font,
    max_width=DESCRIPTION_MAX_WIDTH
):
    """
    Limita a descrição à largura visual da coluna.

    Diferentemente de simplesmente cortar por quantidade
    de caracteres, esta função mede o texto em pixels.

    Quando não couber, adiciona "...".

    Exemplo:

        TEXTO MUITO GRANDE E COM MUITAS INFORMAÇÕES...

    """

    text = clean_text(text)

    if not text:
        return ""

    # --------------------------------------------------------
    # Se já couber inteiro, não altera.
    # --------------------------------------------------------

    if font.measure(text) <= max_width:
        return text

    suffix = "..."

    suffix_width = font.measure(
        suffix
    )

    # --------------------------------------------------------
    # Largura disponível para o texto antes do "..."
    # --------------------------------------------------------

    available_width = (
        max_width - suffix_width
    )

    if available_width <= 0:
        return suffix

    # --------------------------------------------------------
    # Corta progressivamente até caber.
    # --------------------------------------------------------

    truncated = ""

    for char in text:

        candidate = (
            truncated + char
        )

        if font.measure(
            candidate
        ) > available_width:

            break

        truncated = candidate

    # --------------------------------------------------------
    # Evita terminar no meio de uma palavra quando possível.
    # --------------------------------------------------------

    if " " in truncated:

        truncated = truncated.rsplit(
            " ",
            1
        )[0]

    return (
        truncated.rstrip()
        + suffix
    )


# ============================================================
# LIMPEZA DE TEXTO
# ============================================================

def clean_text(value) -> str:
    """
    Remove quebras e espaços duplicados.
    """

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


# ============================================================
# IDENTIFICAÇÃO DE CABEÇALHOS
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
# PARSER DE UMA LINHA DE PRODUTO
# ============================================================

def parse_product_line(
    line,
    page_number=0
):
    """
    Faz uma leitura tolerante de uma linha de produto.

    Estrutura esperada:

    CÓDIGO
    DESCRIÇÃO
    UNID
    CUSTO
    PREÇO
    MÍNIMO
    QUANTIDADE
    NCM
    TOTAL CUSTO
    TOTAL VENDA
    """

    line = clean_text(line)

    if not line:
        return None

    # --------------------------------------------------------
    # Código obrigatoriamente começa a linha.
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Procura a estrutura numérica no FINAL da linha.
    # --------------------------------------------------------

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
    """
    Primeira tentativa de leitura utilizando as tabelas
    identificadas pelo pdfplumber.
    """

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

                    # Remove células completamente vazias.

                    cells = [
                        cell
                        for cell in cells
                        if cell
                    ]

                    if not cells:
                        continue

                    # ------------------------------------------------
                    # CASO 1:
                    # A tabela veio perfeitamente separada.
                    # ------------------------------------------------

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

                        # Verifica se realmente parece produto.

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

                    # ------------------------------------------------
                    # CASO 2:
                    # Tudo dentro de uma célula.
                    # ------------------------------------------------

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
    """
    Fallback para PDFs onde o pdfplumber não consegue montar
    corretamente a tabela.

    Também trata descrições quebradas em várias linhas.
    """

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

                # ----------------------------------------------------
                # Ignora cabeçalhos.
                # ----------------------------------------------------

                if is_noise(line):
                    continue

                # ----------------------------------------------------
                # Novo produto.
                # ----------------------------------------------------

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

                # ----------------------------------------------------
                # Continuação da descrição.
                # ----------------------------------------------------

                elif pending:

                    pending += (
                        " " + line
                    )

            # --------------------------------------------------------
            # Último produto da página.
            # --------------------------------------------------------

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
# LEITOR PRINCIPAL DO PDF
# ============================================================

def extract_products(
    pdf_path: str
):
    """
    Leitor principal.

    Estratégia:

    1. Tenta ler como tabela.
    2. Faz leitura por texto.
    3. Junta os resultados.
    4. Remove duplicidades.
    """

    table_products = []

    text_products = []

    # --------------------------------------------------------
    # TABELAS
    # --------------------------------------------------------

    try:

        table_products = (
            extract_products_from_tables(
                pdf_path
            )
        )

    except Exception:

        table_products = []

    # --------------------------------------------------------
    # TEXTO
    # --------------------------------------------------------

    try:

        text_products = (
            extract_products_from_text(
                pdf_path
            )
        )

    except Exception:

        text_products = []

    # --------------------------------------------------------
    # Junta as duas fontes.
    # --------------------------------------------------------

    all_products = (
        table_products +
        text_products
    )

    # --------------------------------------------------------
    # Remove duplicidades.
    # --------------------------------------------------------

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

            existing_score = sum(
                bool(existing.get(field))
                for field in (
                    "description",
                    "price",
                    "quantity",
                    "ncm",
                )
            )

            new_score = sum(
                bool(product.get(field))
                for field in (
                    "description",
                    "price",
                    "quantity",
                    "ncm",
                )
            )

            if new_score > existing_score:

                unique[code] = product

    return list(
        unique.values()
    )


# ============================================================
# APLICAÇÃO
# ============================================================

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

        # Primeiro clique:
        # maior -> menor

        self.sort_reverse = True

        # ====================================================
        # FONTES
        # ====================================================

        # Fonte utilizada para medir corretamente a largura
        # das descrições.

        self.description_font = tkfont.Font(
            family="Segoe UI",
            size=9
        )

        # ====================================================
        # INTERFACE
        # ====================================================

        self.build_ui()


    # ========================================================
    # INTERFACE
    # ========================================================

    def build_ui(self):

        style = ttk.Style()

        try:

            style.theme_use(
                "clam"
            )

        except Exception:

            pass

        # ----------------------------------------------------
        # TOPO
        # ----------------------------------------------------

        top = ttk.Frame(
            self.root,
            padding=15
        )

        top.pack(
            fill="x"
        )

        ttk.Label(
            top,
            text="Consulta de Preço",
            font=(
                "Segoe UI",
                20,
                "bold"
            )
        ).pack(
            anchor="w"
        )

        ttk.Label(
            top,
            text=(
                "Selecione o PDF, digite o Preço UN. "
                "e copie o código do produto."
            ),
            font=(
                "Segoe UI",
                10
            )
        ).pack(
            anchor="w",
            pady=(2, 12)
        )

        # ----------------------------------------------------
        # CONTROLES
        # ----------------------------------------------------

        controls = ttk.Frame(
            top
        )

        controls.pack(
            fill="x"
        )

        ttk.Button(
            controls,
            text="📄 Selecionar PDF",
            command=self.select_pdf
        ).pack(
            side="left"
        )

        self.file_label = ttk.Label(
            controls,
            text="Nenhum PDF selecionado",
            width=55
        )

        self.file_label.pack(
            side="left",
            padx=12
        )

        ttk.Label(
            controls,
            text="Preço UN.:"
        ).pack(
            side="left",
            padx=(15, 5)
        )

        self.price_var = tk.StringVar()

        self.price_entry = ttk.Entry(
            controls,
            textvariable=self.price_var,
            width=15
        )

        self.price_entry.pack(
            side="left"
        )

        self.price_entry.bind(
            "<Return>",
            lambda e: self.search()
        )

        ttk.Button(
            controls,
            text="🔎 Buscar",
            command=self.search
        ).pack(
            side="left",
            padx=6
        )

        ttk.Button(
            controls,
            text="Limpar",
            command=self.clear_search
        ).pack(
            side="left"
        )

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        self.status_var = tk.StringVar(
            value=(
                "Selecione um PDF para começar."
            )
        )

        ttk.Label(
            top,
            textvariable=self.status_var,
            font=(
                "Segoe UI",
                10
            )
        ).pack(
            anchor="w",
            pady=(10, 0)
        )

        # ----------------------------------------------------
        # RESUMO
        # ----------------------------------------------------

        summary = ttk.Frame(
            self.root,
            padding=(
                15,
                0,
                15,
                8
            )
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
            textvariable=self.result_var
        ).pack(
            side="left"
        )

        ttk.Label(
            summary,
            textvariable=self.copy_var
        ).pack(
            side="right"
        )

        # ----------------------------------------------------
        # ÁREA DA TABELA
        # ----------------------------------------------------

        container = ttk.Frame(
            self.root,
            padding=(
                15,
                0,
                15,
                15
            )
        )

        container.pack(
            fill="both",
            expand=True
        )

        self.canvas = tk.Canvas(
            container,
            highlightthickness=0
        )

        self.scrollbar = ttk.Scrollbar(
            container,
            orient="vertical",
            command=self.canvas.yview
        )

        self.rows_frame = ttk.Frame(
            self.canvas
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

        # Mantém a tabela na largura da janela.

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
    # CONFIGURAÇÃO DAS COLUNAS
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
    # TEXTO DOS BOTÕES DE ORDENAÇÃO
    # ========================================================

    def get_sort_text(
        self,
        title,
        column
    ):

        if self.sort_column == column:

            if self.sort_reverse:

                return (
                    f"{title} ↓"
                )

            return (
                f"{title} ↑"
            )

        return (
            f"{title} ↕"
        )


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

        # ----------------------------------------------------
        # CÓDIGO
        # ----------------------------------------------------

        ttk.Label(
            header,
            text="Código",
            font=(
                "Segoe UI",
                9,
                "bold"
            ),
            anchor="w"
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=3
        )

        # ----------------------------------------------------
        # DESCRIÇÃO
        # ----------------------------------------------------

        ttk.Label(
            header,
            text="Descrição",
            font=(
                "Segoe UI",
                9,
                "bold"
            ),
            anchor="w"
        ).grid(
            row=0,
            column=1,
            sticky="w",
            padx=3
        )

        # ----------------------------------------------------
        # PREÇO
        # ----------------------------------------------------

        ttk.Button(
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

        # ----------------------------------------------------
        # QUANTIDADE
        # ----------------------------------------------------

        ttk.Button(
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

        # ----------------------------------------------------
        # NCM
        # ----------------------------------------------------

        ttk.Label(
            header,
            text="NCM",
            font=(
                "Segoe UI",
                9,
                "bold"
            ),
            anchor="w"
        ).grid(
            row=0,
            column=4,
            sticky="w",
            padx=3
        )

        # ----------------------------------------------------
        # COPIAR
        # ----------------------------------------------------

        ttk.Label(
            header,
            text="Copiar código",
            font=(
                "Segoe UI",
                9,
                "bold"
            ),
            anchor="w"
        ).grid(
            row=0,
            column=5,
            sticky="w",
            padx=3
        )

        # ----------------------------------------------------
        # CÓPIAS
        # ----------------------------------------------------

        ttk.Label(
            header,
            text="Cópias",
            font=(
                "Segoe UI",
                9,
                "bold"
            ),
            anchor="w"
        ).grid(
            row=0,
            column=6,
            sticky="w",
            padx=3
        )

        ttk.Separator(
            self.rows_frame,
            orient="horizontal"
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

            # ------------------------------------------------
            # Reseta resultados.
            # ------------------------------------------------

            self.current_results = (
                self.products.copy()
            )

            # ------------------------------------------------
            # Reseta contadores.
            # ------------------------------------------------

            self.copy_counts.clear()

            self.total_copies = 0

            self.copy_var.set(
                "Total de cópias: 0"
            )

            # ------------------------------------------------
            # Reseta busca.
            # ------------------------------------------------

            self.price_var.set("")

            # ------------------------------------------------
            # Reseta ordenação.
            # ------------------------------------------------

            self.sort_column = None

            self.sort_reverse = True

            # ------------------------------------------------
            # Renderiza.
            # ------------------------------------------------

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
    # BUSCAR POR PREÇO
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

        # ----------------------------------------------------
        # Campo vazio.
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Validação.
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Busca exata no Preço UN.
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Guarda resultado atual.
        # ----------------------------------------------------

        self.current_results = (
            results.copy()
        )

        # ----------------------------------------------------
        # Exibe.
        # ----------------------------------------------------

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
            f"produtos."
        )


    # ========================================================
    # ORDENAR
    # ========================================================

    def sort_products(
        self,
        column
    ):

        if not self.current_results:
            return

        # ----------------------------------------------------
        # Se clicar novamente na mesma coluna,
        # inverte a ordem.
        # ----------------------------------------------------

        if self.sort_column == column:

            self.sort_reverse = (
                not self.sort_reverse
            )

        else:

            self.sort_column = column

            # Primeiro clique:
            # MAIOR -> MENOR

            self.sort_reverse = True

        # ----------------------------------------------------
        # PREÇO
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # QUANTIDADE
        # ----------------------------------------------------

        elif column == "quantity":

            self.current_results.sort(
                key=lambda product:
                    product["quantity"],
                reverse=self.sort_reverse
            )

        # ----------------------------------------------------
        # Atualiza tabela.
        # ----------------------------------------------------

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
        products
    ):

        # Remove widgets antigos.

        for widget in (
            self.rows_frame.winfo_children()
        ):

            widget.destroy()

        # Novo cabeçalho.

        self.make_header()

        # Nenhum resultado.

        if not products:

            ttk.Label(
                self.rows_frame,
                text=(
                    "Nenhum produto encontrado "
                    "para esse preço."
                ),
                font=(
                    "Segoe UI",
                    11
                )
            ).pack(
                pady=30
            )

            return

        # Produtos.

        for product in products:

            self.add_product_row(
                product
            )

        self.canvas.update_idletasks()

        self.canvas.yview_moveto(
            0
        )


    # ========================================================
    # LINHA DO PRODUTO
    # ========================================================

    def add_product_row(
        self,
        product
    ):

        row = ttk.Frame(
            self.rows_frame
        )

        row.pack(
            fill="x",
            pady=4
        )

        # Mesmas colunas do cabeçalho.

        self.configure_columns(
            row
        )

        # ----------------------------------------------------
        # CÓDIGO
        # ----------------------------------------------------

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
        # DESCRIÇÃO
        # ----------------------------------------------------

        # IMPORTANTE:
        #
        # A descrição agora é limitada pela largura visual
        # disponível na coluna.
        #
        # Se for grande demais:
        #
        # "DESCRIÇÃO MUITO GRANDE..."
        #
        # Assim ela nunca invade Preço, Qtd., NCM etc.

        description = truncate_description(
            product["description"],
            self.description_font,
            DESCRIPTION_MAX_WIDTH
        )

        ttk.Label(
            row,
            text=description,
            anchor="w"
        ).grid(
            row=0,
            column=1,
            sticky="w",
            padx=3
        )

        # ----------------------------------------------------
        # PREÇO
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # QUANTIDADE
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # NCM
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # BOTÃO COPIAR
        # ----------------------------------------------------

        copy_button = ttk.Button(
            row,
            text="📋 Copiar",
            command=lambda p=product:
                self.copy_code(p)
        )

        copy_button.grid(
            row=0,
            column=5,
            sticky="w",
            padx=3
        )

        # ----------------------------------------------------
        # CONTADOR
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Guarda referências.
        # ----------------------------------------------------

        product[
            "_quantity_label"
        ] = quantity_label

        product[
            "_copy_button"
        ] = copy_button

        product[
            "_count_label"
        ] = count_label

        # ----------------------------------------------------
        # Se estoque = 0,
        # botão começa bloqueado.
        # ----------------------------------------------------

        if product["quantity"] <= 0:

            copy_button.state(
                ["disabled"]
            )

        # ----------------------------------------------------
        # Divisória.
        # ----------------------------------------------------

        ttk.Separator(
            self.rows_frame,
            orient="horizontal"
        ).pack(
            fill="x"
        )


    # ========================================================
    # COPIAR CÓDIGO
    # ========================================================

    def copy_code(
        self,
        product
    ):

        # ----------------------------------------------------
        # Segurança:
        # estoque zerado não pode copiar.
        # ----------------------------------------------------

        if product["quantity"] <= 0:

            product[
                "_copy_button"
            ].state(
                ["disabled"]
            )

            return

        # ----------------------------------------------------
        # REMOVE ZEROS À ESQUERDA
        #
        # 00000118 -> 118
        # 00001669 -> 1669
        # 00002457 -> 2457
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
        # COPIA PARA CLIPBOARD
        # ----------------------------------------------------

        self.root.clipboard_clear()

        self.root.clipboard_append(
            code
        )

        self.root.update()

        # ----------------------------------------------------
        # DIMINUI UMA UNIDADE
        # ----------------------------------------------------

        product["quantity"] -= 1

        if product["quantity"] < 0:

            product["quantity"] = 0

        # ----------------------------------------------------
        # CONTADOR INDIVIDUAL
        # ----------------------------------------------------

        self.copy_counts[
            product["code"]
        ] += 1

        # ----------------------------------------------------
        # CONTADOR GERAL
        # ----------------------------------------------------

        self.total_copies += 1

        # ----------------------------------------------------
        # ATUALIZA QUANTIDADE
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

        # ----------------------------------------------------
        # ATUALIZA CONTADOR
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # TOTAL
        # ----------------------------------------------------

        self.copy_var.set(
            f"Total de cópias: "
            f"{self.total_copies}"
        )

        # ----------------------------------------------------
        # CHEGOU A ZERO
        # ----------------------------------------------------

        if product["quantity"] <= 0:

            product[
                "_copy_button"
            ].state(
                ["disabled"]
            )


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