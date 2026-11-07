import re
import unicodedata
from decimal import Decimal, InvalidOperation
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

from django.core.exceptions import ValidationError
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException


MAX_CATALOG_ROWS = 5000
MAX_WORKSHEET_ROWS = MAX_CATALOG_ROWS + 30
MAX_WORKSHEET_COLUMNS = 64
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
HEADER_ALIASES = {
    "external_id": {"iddoregistro", "idregistro"},
    "name": {"produtoestoquenome", "nomeproduto", "produto"},
    "order_count": {
        "ndepedidospc",
        "nodepedidospc",
        "numerodepedidospc",
        "pedidos",
    },
    "identification": {"identificacao"},
    "variant_id": {"iddoregistrovariacoesdemarcapn", "idvariacaodemarcapn"},
    "brand": {"marca"},
    "part_number": {"pn", "numerodepeca", "partnumber"},
    "blocked": {"bloqueada", "bloqueado"},
}
FIELD_LIMITS = {
    "external_id": 120,
    "name": 255,
    "identification": 255,
    "variant_id": 120,
    "brand": 120,
    "part_number": 255,
}


def _normalize_header(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _cell_text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _parse_blocked(value):
    normalized = unicodedata.normalize("NFKD", _cell_text(value).strip().lower())
    normalized = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    if normalized in ("", "0", "false", "nao", "n", "no"):
        return False
    if normalized in ("1", "true", "sim", "s", "yes", "x", "bloqueada", "bloqueado"):
        return True
    raise ValueError("valor inválido na coluna de bloqueio; use 0/1, sim/não ou verdadeiro/falso")


def _parse_order_count(value):
    text = _cell_text(value)
    if not text:
        return None
    try:
        number = Decimal(text.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("número de pedidos inválido") from exc
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError("número de pedidos deve ser um inteiro igual ou maior que zero")
    return int(number)


def _find_columns(values):
    columns = {}
    for index, value in enumerate(values):
        normalized = _normalize_header(value)
        if not normalized:
            continue
        for field, aliases in HEADER_ALIASES.items():
            if normalized in aliases and field not in columns:
                columns[field] = index

    missing = [field for field in ("external_id", "name") if field not in columns]
    if missing:
        raise ValidationError(
            "Não encontrei as colunas obrigatórias de ID do registro e nome do produto."
        )
    return columns


def parse_catalog_workbook(uploaded_file):
    try:
        workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
    except (OSError, ValueError, KeyError, BadZipFile, InvalidFileException, ParseError) as exc:
        raise ValidationError("Não foi possível abrir o arquivo. Envie uma planilha .xlsx válida.") from exc

    try:
        worksheet = workbook.active
        if (
            worksheet.max_column is not None
            and worksheet.max_column > MAX_WORKSHEET_COLUMNS
        ):
            raise ValidationError(
                f"A planilha deve ter no máximo {MAX_WORKSHEET_COLUMNS} colunas."
            )
        if (
            worksheet.max_row is not None
            and worksheet.max_row > MAX_WORKSHEET_ROWS
        ):
            raise ValidationError(
                f"A planilha deve ter no máximo {MAX_CATALOG_ROWS} linhas de produtos."
            )
        header_row = None
        columns = None
        for row_number, values in enumerate(
            worksheet.iter_rows(min_row=1, max_row=30, values_only=True), start=1
        ):
            try:
                columns = _find_columns(values)
            except ValidationError:
                continue
            header_row = row_number
            break
        if header_row is None:
            raise ValidationError(
                "Não encontrei um cabeçalho com as colunas obrigatórias de ID do registro e nome do produto."
            )

        products = []
        errors = []
        seen_products = set()
        row_count = 0
        for row_number, values in enumerate(
            worksheet.iter_rows(min_row=header_row + 1, values_only=True),
            start=header_row + 1,
        ):
            if not any(value is not None and _cell_text(value) for value in values):
                continue
            row_count += 1
            if row_count > MAX_CATALOG_ROWS:
                raise ValidationError(
                    f"A planilha excede o limite de {MAX_CATALOG_ROWS} produtos por importação."
                )

            try:
                product = {}
                for field in FIELD_LIMITS:
                    column = columns.get(field)
                    value = _cell_text(values[column]) if column is not None and column < len(values) else ""
                    if field in ("external_id", "name") and not value:
                        raise ValueError(
                            "ID do registro e nome do produto são obrigatórios"
                        )
                    if len(value) > FIELD_LIMITS[field]:
                        raise ValueError(
                            f"o campo {field} excede {FIELD_LIMITS[field]} caracteres"
                        )
                    product[field] = value

                order_column = columns.get("order_count")
                product["order_count"] = _parse_order_count(
                    values[order_column] if order_column is not None and order_column < len(values) else None
                )
                blocked_column = columns.get("blocked")
                product["blocked"] = _parse_blocked(
                    values[blocked_column] if blocked_column is not None and blocked_column < len(values) else None
                )
                product_key = (product["external_id"], product["variant_id"])
                if product_key in seen_products:
                    raise ValueError("ID do registro e ID da variação repetidos nesta planilha")
                seen_products.add(product_key)
                products.append(product)
            except (ValueError, InvalidOperation) as exc:
                errors.append({"row": row_number, "message": str(exc)})

        if not products and not errors:
            raise ValidationError("A planilha não contém produtos abaixo do cabeçalho.")
        return products, errors, row_count
    except ValidationError:
        raise
    except (OSError, ValueError, KeyError, BadZipFile, InvalidFileException, ParseError) as exc:
        raise ValidationError(
            "Não foi possível ler a planilha. Envie um arquivo .xlsx válido."
        ) from exc
    finally:
        workbook.close()
