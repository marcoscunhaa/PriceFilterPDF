import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from collections import defaultdict

import pdfplumber


# ============================================================
# CONFIGURAÇÕES DAS COLUNAS
# ============================================================

# Essas larguras são usadas TANTO no cabeçalho quanto nos produtos.
# Isso garante que tudo fique perfeitamente alinhado.
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
# LEITOR DO PDF
# ============================================================

PRODUCT_RE = re.compile(
    r"^(?P<code>\d{4,})\s+"
    r"(?P<desc>.*?)\s+"
    r"(?P<unit>[A-Za-zÀ-ÿ]+)\s+"
    r"(?P<cost>[\d.]+,\d{2})\s+"
    r"(?P<price>[\d.]+,\d{2})\s+"
    r"(?P<min>[\d.]+,\d{2})\s+"
    r"(?P<qty>[\d.]+(?:,\d{2})?)\s+"
    r"(?P<ncm>\d{4}\.\d{2}\.\d{2})\s+"
    r"(?P<total_cost>[\d.]+,\d{2})\s+"
    r"(?P<total_price>[\d.]+,\d{2})$"
)


HEADER_WORDS = (
    "código",
    "codigo",
    "descrição",
    "descricao",
    "grupo mercadoria",
    "custo un",
    "preço un",
    "preco un",
    "ncm",
    "registros:"
)


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


def br_money(value: str) -> str:
    """
    Exibe número no padrão brasileiro.
    """

    try:
        number = float(normalize_money(value))

        return (
            f"{number:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    except Exception:
        return value


def format_quantity(value) -> str:
    """
    Formata quantidade para exibição.

    1072.0 -> 1072
    5.0    -> 5
    """

    try:
        number = float(value)

        if number.is_integer():
            return str(int(number))

        return f"{number:.2f}".replace(".", ",")

    except Exception:
        return str(value)


def is_noise(line: str) -> bool:
    """
    Ignora linhas de cabeçalho e informações que não são produtos.
    """

    low = line.lower().strip()

    if not low:
        return True

    return any(word in low for word in HEADER_WORDS)


def parse_product(line: str):
    """
    Tenta transformar uma linha do PDF em um produto.
    """

    match = PRODUCT_RE.match(line)

    if not match:
        return None

    data = match.groupdict()

    try:
        quantity = float(
            normalize_money(data["qty"])
        )

    except ValueError:
        return None

    return {
        "code": data["code"],
        "description": data["desc"].strip(),
        "unit": data["unit"],
        "cost": data["cost"],
        "price": data["price"],
        "minimum": data["min"],
        "quantity": quantity,
        "ncm": data["ncm"],
        "total_cost": data["total_cost"],
        "total_price": data["total_price"],
    }


def extract_products(pdf_path: str):
    """
    Lê o PDF inteiro e extrai os produtos.
    """

    products = []

    pending = None

    with pdfplumber.open(pdf_path) as pdf:

        for page_number, page in enumerate(
            pdf.pages,
            start=1
        ):

            text = page.extract_text(
                x_tolerance=2,
                y_tolerance=3
            ) or ""

            lines = [
                re.sub(r"\s+", " ", x).strip()
                for x in text.splitlines()
            ]

            for line in lines:

                if not line or is_noise(line):
                    continue

                # Detecta início de um novo produto
                if re.match(r"^\d{4,}\s+", line):

                    # Finaliza produto anterior
                    if pending:

                        product = parse_product(
                            pending
                        )

                        if product:
                            product["page"] = page_number
                            products.append(product)

                    pending = line

                elif pending:

                    # Caso a descrição tenha quebrado em outra linha
                    if not any(
                        x in line.lower()
                        for x in (
                            "registros:",
                            "custo un.",
                            "preço un."
                        )
                    ):
                        pending += " " + line

            # Finaliza produto no fim da página
            if pending:

                product = parse_product(
                    pending
                )

                if product:
                    product["page"] = page_number
                    products.append(product)

                pending = None

    # Remove duplicidades
    unique = {}

    for product in products:

        key = (
            product["code"],
            product["price"],
            product["description"]
        )

        unique[key] = product

    return list(unique.values())


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

        # Produtos carregados
        self.products = []

        # Quantidade de vezes que cada código foi copiado
        self.copy_counts = defaultdict(int)

        # Total geral de cópias
        self.total_copies = 0

        # PDF atual
        self.current_pdf = ""

        self.build_ui()


    # ========================================================
    # INTERFACE
    # ========================================================

    def build_ui(self):

        style = ttk.Style()

        try:
            style.theme_use("clam")

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

        controls = ttk.Frame(top)

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
            value="Selecione um PDF para começar."
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
            padding=(15, 0, 15, 8)
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
            padding=(15, 0, 15, 15)
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
                    scrollregion=self.canvas.bbox("all")
                )
        )


        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.rows_frame,
            anchor="nw"
        )


        self.canvas.configure(
            yscrollcommand=self.scrollbar.set
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


        # Faz o conteúdo acompanhar a largura da janela
        self.canvas.bind(
            "<Configure>",
            lambda e:
                self.canvas.itemconfig(
                    self.canvas_window,
                    width=e.width
                )
        )


        # Começa com tabela vazia
        self.render_rows([])


    # ========================================================
    # CONFIGURAÇÃO DAS COLUNAS
    # ========================================================

    def configure_columns(self, frame):

        """
        Configura as colunas.

        IMPORTANTE:

        Esse método é usado tanto pelo cabeçalho
        quanto pelas linhas dos produtos.

        Portanto os dois ficam exatamente alinhados.
        """

        for column, width in COL_WIDTHS.items():

            frame.grid_columnconfigure(
                column,
                minsize=width,
                weight=0
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


        # Usa exatamente as mesmas colunas
        # usadas nas linhas.
        self.configure_columns(
            header
        )


        headers = [
            ("Código", 0),
            ("Descrição", 1),
            ("Preço UN.", 2),
            ("Qtd.", 3),
            ("NCM", 4),
            ("Copiar código", 5),
            ("Cópias", 6),
        ]


        for text, column in headers:

            ttk.Label(
                header,
                text=text,
                font=(
                    "Segoe UI",
                    9,
                    "bold"
                ),
                anchor="w"
            ).grid(
                row=0,
                column=column,
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
            title="Selecione o relatório PDF",
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

            self.products = extract_products(
                path
            )


            # Zera contadores
            self.copy_counts.clear()

            self.total_copies = 0


            self.copy_var.set(
                "Total de cópias: 0"
            )


            self.price_var.set("")


            self.render_rows(
                self.products
            )


            if self.products:

                self.status_var.set(
                    f"PDF carregado: "
                    f"{len(self.products)} "
                    f"produtos encontrados."
                )

            else:

                self.status_var.set(
                    "Não consegui identificar "
                    "produtos neste PDF."
                )


                messagebox.showwarning(
                    "PDF não reconhecido",
                    (
                        "O PDF foi aberto, mas o formato "
                        "das linhas não foi reconhecido."
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
    # BUSCAR
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

            self.render_rows(
                self.products
            )

            self.result_var.set(
                f"Resultados: "
                f"{len(self.products)}"
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


            except ValueError:
                pass


        self.render_rows(
            results
        )


        self.result_var.set(
            f"Resultados: {len(results)}"
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


        self.render_rows(
            self.products
        )


        self.result_var.set(
            f"Resultados: "
            f"{len(self.products)}"
        )


        self.status_var.set(
            f"Exibindo todos os "
            f"{len(self.products)} produtos."
        )


    # ========================================================
    # RENDERIZAR TABELA
    # ========================================================

    def render_rows(self, products):

        # Remove tudo antes de reconstruir.
        # Isso evita cabeçalho duplicado.
        for widget in self.rows_frame.winfo_children():

            widget.destroy()


        # Cria novo cabeçalho
        self.make_header()


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


        # Cria cada produto
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

    def add_product_row(self, product):

        row = ttk.Frame(
            self.rows_frame
        )


        row.pack(
            fill="x",
            pady=4
        )


        # MESMAS COLUNAS DO CABEÇALHO
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

        ttk.Label(
            row,
            text=product["description"],
            anchor="w"
        ).grid(
            row=0,
            column=1,
            sticky="w",
            padx=3
        )


        # ----------------------------------------------------
        # PREÇO UN.
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


        # Guarda referências para podermos
        # atualizar depois do clique.
        product["_quantity_label"] = (
            quantity_label
        )

        product["_copy_button"] = (
            copy_button
        )

        product["_count_label"] = (
            count_label
        )


        # Se já estiver zerado,
        # começa desabilitado.
        if product["quantity"] <= 0:

            copy_button.state(
                ["disabled"]
            )


        ttk.Separator(
            self.rows_frame,
            orient="horizontal"
        ).pack(
            fill="x"
        )


    # ========================================================
    # COPIAR CÓDIGO
    # ========================================================

    def copy_code(self, product):

        # Segurança:
        # nunca permite copiar com estoque zerado.
        if product["quantity"] <= 0:

            product["_copy_button"].state(
                ["disabled"]
            )

            return


        # ----------------------------------------------------
        # REMOVE ZEROS À ESQUERDA
        # ----------------------------------------------------
        #
        # 00000118 -> 118
        # 00001669 -> 1669
        # 00002457 -> 2457
        #

        code = str(
            int(
                product["code"]
            )
        )


        # ----------------------------------------------------
        # COPIA PARA O CLIPBOARD
        # ----------------------------------------------------

        self.root.clipboard_clear()

        self.root.clipboard_append(
            code
        )

        self.root.update()


        # ----------------------------------------------------
        # DIMINUI 1 UNIDADE
        # ----------------------------------------------------

        product["quantity"] -= 1


        # Segurança adicional
        # contra qualquer valor negativo.
        if product["quantity"] < 0:

            product["quantity"] = 0


        # ----------------------------------------------------
        # ATUALIZA CONTADOR
        # ----------------------------------------------------

        self.copy_counts[
            product["code"]
        ] += 1


        self.total_copies += 1


        # ----------------------------------------------------
        # ATUALIZA QUANTIDADE NA TELA
        # ----------------------------------------------------

        if (
            product.get("_quantity_label")
            and
            product[
                "_quantity_label"
            ].winfo_exists()
        ):

            product[
                "_quantity_label"
            ].config(
                text=format_quantity(
                    product["quantity"]
                )
            )


        # ----------------------------------------------------
        # ATUALIZA CONTADOR DE CÓPIAS
        # ----------------------------------------------------

        if (
            product.get("_count_label")
            and
            product[
                "_count_label"
            ].winfo_exists()
        ):

            product[
                "_count_label"
            ].config(
                text=str(
                    self.copy_counts[
                        product["code"]
                    ]
                )
            )


        # ----------------------------------------------------
        # TOTAL GERAL
        # ----------------------------------------------------

        self.copy_var.set(
            f"Total de cópias: "
            f"{self.total_copies}"
        )


        # ----------------------------------------------------
        # SE CHEGOU A ZERO, DESABILITA
        # ----------------------------------------------------

        if product["quantity"] <= 0:

            product[
                "_copy_button"
            ].state(
                ["disabled"]
            )


# ============================================================
# INICIALIZAÇÃO
# ============================================================

def main():

    root = tk.Tk()

    App(root)

    root.mainloop()


if __name__ == "__main__":

    main()