from django.shortcuts import render
from difflib import SequenceMatcher
from .forms import UploadFilesForm
import pandas as pd
import re
from io import BytesIO
from django.http import HttpResponse
from django.core.files.uploadedfile import InMemoryUploadedFile
from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from zipfile import ZipFile
from html import escape
FD_UNMATCHED = None
GL_UNMATCHED = None
FD_MATCHED = None
GL_MATCHED = None
THIRD_UNMATCHED = None
RECONCILED_STATEMENT = None
FD_GL_MATCHED_DISPLAY = None
GL_THIRD_MATCHED_DISPLAY = None
USER_RESULTS = {}

TEXT_COLUMN_NAMES = {
    "details",
    "narration",
    "description",
    "particulars",
    "transactiondetails",
    "transactiondescription",
    "remarks",
}
AMOUNT_COLUMN_NAMES = {
    "amount",
    "debit",
    "credit",
    "debitamount",
    "creditamount",
    "dr",
    "cr",
    "withdrawal",
    "deposit",
}
DATE_COLUMN_NAMES = {
    "date",
    "transactiondate",
    "valuedate",
    "postingdate",
}
BALANCE_COLUMN_NAMES = {
    "balance",
    "runningbalance",
    "closingbalance",
    "ledgerbalance",
}
CREDIT_COLUMN_NAMES = {
    "credit",
    "creditamount",
    "cr",
    "deposit",
    "lodgement",
    "lodgements",
}
DEBIT_COLUMN_NAMES = {
    "debit",
    "debitamount",
    "dr",
    "withdrawal",
    "withdrawals",
}
SIGNED_AMOUNT_COLUMN_NAMES = {
    "amount",
    "transactionamount",
}

GENERIC_PREFIXES = {
    "access","fbn","gtb","uba","union","zenith","sterling","wema","polaris","acess","accss","microfinance","micro","finance","fcmb","to","of","co",
    "good","shepherd","shepher","pos", "charge", "atm", "wdl", "trf", "transfer","keystone","ussd-nip","goo","moniepoint","st","eze",
    "nibss", "vat","for","ven","mr","mrs","miss", "stamp", "fee", "reversal","ifo","iro","nip","chq","onb", "usd","ussd","payment","deposit","dep",
    "mob","mobile","microfinanc","ranfer","&amp","uto","frm","from","ltd","lt","eco","bnk","bank","ang","zbn","bk","com","comp","company","enugu","enu","en",
    "electronic","money","levy","on","autopay","transaction","auto","cleared"
    }

MIN_WORD_LEN = 2
SCORE_THRESHOLD = 70
BANK_ALIASES = {
    "aces": "access",
    "acess": "access",
    "accss": "access",
    "access": "access",
    "eco": "eco",
    "fbn": "fbn",
    "polaris": "polaris",
    "uba": "uba",
    "union": "union",
    "zbn": "zenith",
    "zenith": "zenith",
}

def remove_unnamed_columns(dataframe):
    dataframe = dataframe.rename(columns=lambda column: str(column).strip())

    return dataframe.loc[
        :,
        [
            column for column in dataframe.columns
            if not str(column).strip().lower().startswith("unnamed")
        ],
    ]

def normalize_text(text):
    if pd.isna(text):
        return []

    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    tokens = [
        t for t in text.split()
        if len(t) >= MIN_WORD_LEN and t not in GENERIC_PREFIXES and not t.isdigit()
    ]

    return tokens

def normalize_all_text(text):
    if pd.isna(text):
        return []

    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return [
        t for t in text.split()
        if len(t) >= MIN_WORD_LEN and not t.isdigit()
    ]

def normalize_reference_tokens(text):
    if pd.isna(text):
        return []

    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return [
        t for t in text.split()
        if len(t) >= 3 and any(character.isdigit() for character in t)
    ]

def normalize_short_reference_tokens(text):
    if pd.isna(text):
        return []

    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return [
        t for t in text.split()
        if len(t) >= 2 and t.isdigit()
    ]

def normalize_bank_tokens(text):
    if pd.isna(text):
        return []

    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return [
        BANK_ALIASES[t]
        for t in text.split()
        if t in BANK_ALIASES
    ]

def normalize_amount(value):
    amount = normalize_signed_amount(value)

    if amount is None:
        return None

    return amount.copy_abs()

def normalize_signed_amount(value):
    if pd.isna(value):
        return None

    try:
        amount_text = str(value).replace(",", "").strip()
        if amount_text.startswith("(") and amount_text.endswith(")"):
            amount_text = f"-{amount_text[1:-1]}"

        return Decimal(amount_text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, AttributeError):
        return None

def amounts_equal(first_amount, second_amount):
    first_amount = normalize_amount(first_amount)
    second_amount = normalize_amount(second_amount)

    return first_amount is not None and second_amount is not None and first_amount == second_amount

def normalize_column_name(column):
    return re.sub(r"[^a-z0-9]", "", str(column).lower())

def get_row_amounts(row):
    return [
        amount_detail["amount"]
        for amount_detail in get_row_amount_details(row)
    ]

def get_row_amount_details(row):
    amount_details = []

    for column in row.index:
        if normalize_column_name(column) not in AMOUNT_COLUMN_NAMES:
            continue

        amount = normalize_amount(row[column])
        if amount is not None and amount != Decimal("0.00"):
            amount_details.append({
                "amount": amount,
                "column": column,
                "value": row[column],
            })

    return amount_details

def get_row_sided_amounts(row):
    return [
        (amount_detail["side"], amount_detail["amount"])
        for amount_detail in get_row_sided_amount_details(row)
    ]

def get_row_sided_amount_details(row):
    sided_amount_details = []

    for column in row.index:
        normalized_column = normalize_column_name(column)
        amount = normalize_signed_amount(row[column])

        if amount is None or amount == Decimal("0.00"):
            continue

        if normalized_column in CREDIT_COLUMN_NAMES:
            sided_amount_details.append({
                "side": "credit",
                "amount": amount.copy_abs(),
                "column": column,
                "value": row[column],
            })
        elif normalized_column in DEBIT_COLUMN_NAMES:
            sided_amount_details.append({
                "side": "debit",
                "amount": amount.copy_abs(),
                "column": column,
                "value": row[column],
            })
        elif normalized_column in SIGNED_AMOUNT_COLUMN_NAMES:
            if amount > 0:
                sided_amount_details.append({
                    "side": "credit",
                    "amount": amount,
                    "column": column,
                    "value": row[column],
                })
            elif amount < 0:
                sided_amount_details.append({
                    "side": "debit",
                    "amount": amount.copy_abs(),
                    "column": column,
                    "value": row[column],
                })

    return sided_amount_details

def get_row_values_by_side(row, side):
    return [
        amount
        for row_side, amount in get_row_sided_amounts(row)
        if row_side == side
    ]

def get_row_text(row):
    for column in row.index:
        if normalize_column_name(column) in TEXT_COLUMN_NAMES:
            return row[column]

    text_values = []
    for column in row.index:
        if normalize_column_name(column) in AMOUNT_COLUMN_NAMES:
            continue

        value = row[column]
        if pd.notna(value):
            text_values.append(str(value))

    return " ".join(text_values)

def normalize_text_key(text):
    return " ".join(normalize_all_text(text))

def rows_have_same_text(first_row, second_row):
    first_text = normalize_text_key(get_row_text(first_row))
    second_text = normalize_text_key(get_row_text(second_row))

    return bool(first_text and second_text and first_text == second_text)

def third_document_row_matches_gl_row(third_row, gl_row):
    third_amounts = get_row_amounts(third_row)
    gl_amounts = get_row_amounts(gl_row)
    same_text = rows_have_same_text(third_row, gl_row)

    #print(f"--- Comparing ---")
    #print(f"Third text: {get_row_text(third_row)}")
    #print(f"GL text:    {get_row_text(gl_row)}")
    #print(f"Third amounts: {third_amounts}")
    #print(f"GL amounts:    {gl_amounts}")
    #print(f"Same text: {same_text}")
    
    if same_text:
        if third_amounts and gl_amounts:
            result = bool(set(third_amounts) & set(gl_amounts))
        else:
            result = True
        return result

    result = bool(third_amounts and gl_amounts and rows_match(third_row, gl_row))
    return result

def amount_matches(fd_row, gl_row):
    fd_credits = set(get_row_values_by_side(fd_row, "credit"))
    fd_debits = set(get_row_values_by_side(fd_row, "debit"))
    gl_credits = set(get_row_values_by_side(gl_row, "credit"))
    gl_debits = set(get_row_values_by_side(gl_row, "debit"))

    return bool((fd_credits & gl_debits) or (fd_debits & gl_credits))

def has_two_word_overlap(fd_tokens, gl_tokens):
    return len(set(fd_tokens) & set(gl_tokens)) >= 2

def has_reference_match(fd_tokens, gl_tokens):
    return bool(set(fd_tokens) & set(gl_tokens))

def has_cheque_reference_match(fd_references, gl_references, fd_banks, gl_banks):
    return (
        bool(set(fd_references) & set(gl_references)) and
        bool(set(fd_banks) & set(gl_banks))
    )

def has_compact_name_match(fd_tokens, gl_tokens):
    if not fd_tokens or not gl_tokens:
        return False

    fd_compact = "".join(fd_tokens)
    gl_compact = "".join(gl_tokens)

    if len(fd_compact) < 6 or len(gl_compact) < 6:
        return False

    return fd_compact in gl_compact or gl_compact in fd_compact

def has_meaningful_match(fd_tokens, gl_tokens):
    if not fd_tokens or not gl_tokens:
        return False

    overlap_count = len(set(fd_tokens) & set(gl_tokens))
    required_overlap = 2

    if len(set(fd_tokens)) < 2 or len(set(gl_tokens)) < 2:
        required_overlap = 1

    return overlap_count >= required_overlap

def is_generic_only_match(fd_all_tokens, gl_all_tokens, fd_tokens, gl_tokens):
    if fd_tokens or gl_tokens:
        return False

    return bool(set(fd_all_tokens) & set(gl_all_tokens))

def rows_match(fd_row, gl_row):
    if not amount_matches(fd_row, gl_row):
        return False

    fd_text = get_row_text(fd_row)
    gl_text = get_row_text(gl_row)

    fd_all_tokens = normalize_all_text(fd_text)
    gl_all_tokens = normalize_all_text(gl_text)
    fd_reference_tokens = normalize_reference_tokens(fd_text)
    gl_reference_tokens = normalize_reference_tokens(gl_text)
    fd_short_references = normalize_short_reference_tokens(fd_text)
    gl_short_references = normalize_short_reference_tokens(gl_text)
    fd_bank_tokens = normalize_bank_tokens(fd_text)
    gl_bank_tokens = normalize_bank_tokens(gl_text)
    fd_tokens = normalize_text(fd_text)
    gl_tokens = normalize_text(gl_text)

    return (
        has_meaningful_match(fd_tokens, gl_tokens) or
        has_compact_name_match(fd_tokens, gl_tokens) or
        has_reference_match(fd_reference_tokens, gl_reference_tokens) or
        has_cheque_reference_match(fd_short_references, gl_short_references, fd_bank_tokens, gl_bank_tokens) or
        is_generic_only_match(fd_all_tokens, gl_all_tokens, fd_tokens, gl_tokens)
    )

def strip_prefix(words):
    stripped = words[:]

    while stripped and stripped[0] in GENERIC_PREFIXES:
        stripped.pop(0)

    return stripped

def ordered_match_score(fd_words, gl_words):
    if not fd_words or not gl_words:
        return 0

    fd_str = " ".join(fd_words)
    gl_str = " ".join(gl_words)
    similarity = SequenceMatcher(None, fd_str, gl_str).ratio()

    if similarity >= 0.9:
        return 100
    elif similarity >= 0.75:
        return 70
    elif similarity >= 0.6:
        return 50
    elif similarity >= 0.5:
        return 40
    elif similarity >= 0.4:
        return 30
    elif similarity >= 0.3:
        return 20
    else:
        return 0

def has_minimum_word_match(fd_tokens, gl_tokens):
    if not fd_tokens or not gl_tokens:
        return False

    return bool(set(fd_tokens) & set(gl_tokens))


def match_logic_with_matches(fd, gl):
    outFD, outGL = [], []
    matched_gl_indices = set()

    for x in fd.index:
        for i in gl.index:
            if i in matched_gl_indices:
                continue

            if rows_match(fd.loc[x], gl.loc[i]):
                outFD.append(x)
                outGL.append(i)
                matched_gl_indices.add(i)
                break
   
 
    FD_matched = fd.loc[outFD].reset_index(drop=True)
    GL_matched = gl.loc[outGL].reset_index(drop=True)
    FD_unmatched = fd.drop(outFD)
    GL_unmatched = gl.drop(outGL)

    return FD_unmatched, GL_unmatched, FD_matched, GL_matched

def match_logic(fd, gl):
    FD_unmatched, GL_unmatched, _, _ = match_logic_with_matches(fd, gl)

    return FD_unmatched, GL_unmatched

def build_matched_reconciled_statement(fd_matched, gl_matched):
    fd_side = fd_matched.reset_index(drop=True).add_prefix("FD ")
    gl_side = gl_matched.reset_index(drop=True).add_prefix("GL ")

    return pd.concat([fd_side, gl_side], axis=1)

def find_opposite_side_matched_amounts(first_row, second_row):
    for first_amount in get_row_sided_amount_details(first_row):
        for second_amount in get_row_sided_amount_details(second_row):
            if first_amount["amount"] != second_amount["amount"]:
                continue

            if first_amount["side"] == second_amount["side"]:
                continue

            return first_amount["value"], second_amount["value"]

    return "", ""

def find_same_amount_values(first_row, second_row):
    for first_amount in get_row_amount_details(first_row):
        for second_amount in get_row_amount_details(second_row):
            if first_amount["amount"] == second_amount["amount"]:
                return first_amount["value"], second_amount["value"]

    return "", ""

def find_third_file_matched_amounts(gl_row, third_row):
    gl_amount, third_amount = find_same_amount_values(gl_row, third_row)

    if gl_amount != "" or third_amount != "":
        return gl_amount, third_amount

    return find_opposite_side_matched_amounts(gl_row, third_row)

def build_paired_matched_rows(first_matched, second_matched, first_label, second_label, amount_resolver):
    rows = []

    for index in range(min(len(first_matched), len(second_matched))):
        first_row = first_matched.iloc[index]
        second_row = second_matched.iloc[index]
        first_amount, second_amount = amount_resolver(first_row, second_row)

        rows.append({
            f"{first_label} Narration": get_row_text(first_row),
            f"{first_label} Amount": first_amount,
            f"{second_label} Narration": get_row_text(second_row),
            f"{second_label} Amount": second_amount,
        })

    return pd.DataFrame(
        rows,
        columns=[
            f"{first_label} Narration",
            f"{first_label} Amount",
            f"{second_label} Narration",
            f"{second_label} Amount",
        ],
    )

def build_fd_gl_matched_display(fd_matched, gl_matched):
    return build_paired_matched_rows(
        fd_matched,
        gl_matched,
        "Bank Statement",
        "GL",
        find_opposite_side_matched_amounts,
    )

def build_gl_third_matched_display(gl_matched, third_matched):
    return build_paired_matched_rows(
        gl_matched,
        third_matched,
        "GL",
        "Third File",
        find_third_file_matched_amounts,
    )

def get_first_value_by_column_names(row, column_names):
    for column in row.index:
        if normalize_column_name(column) in column_names and pd.notna(row[column]):
            return row[column]

    return ""

def get_last_gl_balance(gl):
    for column in gl.columns:
        if normalize_column_name(column) not in BALANCE_COLUMN_NAMES:
            continue

        for value in reversed(gl[column].tolist()):
            amount = normalize_signed_amount(value)
            if amount is not None:
                return amount

    return Decimal("0.00")

def get_row_date(row):
    return get_first_value_by_column_names(row, DATE_COLUMN_NAMES)

def build_statement_entries(dataframe, side):
    entries = []

    for _, row in dataframe.iterrows():
        for amount in get_row_values_by_side(row, side):
            entries.append({
                "Date": get_row_date(row),
                "Narration": get_row_text(row),
                "Amount": amount,
                "": "",
            })

    return entries

def append_statement_section(rows, title, entries, include_title):
    if not entries:
        return

    if include_title:
        rows.append({"Date": "", "Narration": title, "Amount": "", "": ""})

    rows.extend(entries)

def build_reconciled_statement(gl, fd_unmatched, gl_unmatched, third_unmatched, include_section_titles=False):
    running_balance = get_last_gl_balance(gl)
    rows = [
        {"Date": "", "Narration": "Last GL Balance", "Amount": "", "": running_balance},
    ]

    credit_sections = [
        ("Add Unmatched Credit Bank statement", build_statement_entries(fd_unmatched, "credit")),
        ("Add Unmatched Credit GL", build_statement_entries(gl_unmatched, "credit")),
        ("Add Unmatched Credit Report file", build_statement_entries(third_unmatched, "credit")),
    ]

    for title, entries in credit_sections:
        append_statement_section(rows, title, entries, include_section_titles)
        running_balance += sum((entry["Amount"] for entry in entries), Decimal("0.00"))

    rows.append({"Date": "", "Narration": "Total", "Amount": "", "": running_balance})
    

    debit_sections = [
        ("Less Unmatched Debit Bank statement", build_statement_entries(fd_unmatched, "debit")),
        ("Less Unmatched Debit GL", build_statement_entries(gl_unmatched, "debit")),
        ("Less Unmatched Debit Report file", build_statement_entries(third_unmatched, "debit")),
    ]

    for title, entries in debit_sections:
        append_statement_section(rows, title, entries, include_section_titles)
        running_balance -= sum((entry["Amount"] for entry in entries), Decimal("0.00"))

    rows.append({"Date": "", "Narration": "Final Balance", "Amount": "", "": running_balance})

    return pd.DataFrame(rows, columns=["Date", "Narration", "Amount", ""])

def is_empty_table_value(value):
    return pd.isna(value) or str(value).strip() == ""

def format_table_value(value):
    if is_empty_table_value(value):
        return ""

    return escape(str(value))

def dataframe_to_html(dataframe, classes="table table-bordered", bold_empty_amount_narration=False):
    class_attribute = f'dataframe {classes}'
    header_cells = "".join(
        f"<th>{escape(str(column))}</th>"
        for column in dataframe.columns
    )
    body_rows = []

    for _, row in dataframe.iterrows():
        body_cells = []

        for column in dataframe.columns:
            cell_value = format_table_value(row[column])

            if (
                bold_empty_amount_narration
                and column == "Narration"
                and is_empty_table_value(row.get("Amount"))
                and cell_value
            ):
                cell_value = f"<strong>{cell_value}</strong>"

            body_cells.append(f"<td>{cell_value}</td>")

        body_rows.append(f"<tr>{''.join(body_cells)}</tr>")

    return (
        f'<table border="1" class="{class_attribute}">'
        f"<thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        f"</table>"
    )

def apply_third_file_to_gl_unmatched_with_matches(third_file, gl_unmatched):
    third_document = remove_unnamed_columns(pd.read_excel(third_file))
    #third_document = third_file
    matched_gl_indices = set()
    matched_third_indices = set()
    matched_gl_rows = []
    matched_third_rows = []
    
    #print("=== GL UNMATCHED INDICES ===")
    #print(gl_unmatched.index.tolist())
    #print("=== THIRD DOC INDICES ===")
    #print(third_document.index.tolist())
    
    for gl_index in gl_unmatched.index:
        for third_index in third_document.index:
            result = third_document_row_matches_gl_row(
                third_document.loc[third_index], 
                gl_unmatched.loc[gl_index]
            )
            if result:
                #print(f"=== MATCH FOUND ===")
                #print(f"GL index {gl_index}: {gl_unmatched.loc[gl_index].to_dict()}")
                #print(f"Third index {third_index}: {third_document.loc[third_index].to_dict()}")
                matched_gl_indices.add(gl_index)
                matched_third_indices.add(third_index)
                matched_gl_rows.append(gl_unmatched.loc[gl_index])
                matched_third_rows.append(third_document.loc[third_index])
                break

    #print("=== MATCHED GL INDICES ===")
    #print(matched_gl_indices)
    
    final_gl_unmatched = gl_unmatched.loc[
        ~gl_unmatched.index.isin(matched_gl_indices)
    ].reset_index(drop=True)
    
    #print("=== FINAL GL UNMATCHED ===")
    #print(final_gl_unmatched)
    
    third_unmatched = third_document.loc[
        ~third_document.index.isin(matched_third_indices)
    ].reset_index(drop=True)

    gl_matched = pd.DataFrame(matched_gl_rows).reset_index(drop=True)
    third_matched = pd.DataFrame(matched_third_rows).reset_index(drop=True)

    return final_gl_unmatched, third_unmatched, gl_matched, third_matched

def apply_third_file_to_gl_unmatched(third_file, gl_unmatched):
    final_gl_unmatched, third_unmatched, _, _ = apply_third_file_to_gl_unmatched_with_matches(
        third_file,
        gl_unmatched,
    )

    return final_gl_unmatched, third_unmatched


def save_user_results(user, **results):
    USER_RESULTS[user.pk] = results

def get_user_result(request, key):
    return USER_RESULTS.get(request.user.pk, {}).get(key)


def download_dataframe(dataframe, filename):
    if dataframe is None:
        return HttpResponse("No file to download")

    buffer = BytesIO()
    dataframe.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    return HttpResponse(
        buffer,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def build_download_items(results):
    return [
        ("FD_Unmatched.xlsx", results.get("fd_unmatched")),
        ("GL_Unmatched.xlsx", results.get("gl_unmatched")),
        ("Third_Unmatched.xlsx", results.get("third_unmatched")),
        ("FD_Matched.xlsx", results.get("fd_matched")),
        ("GL_Matched.xlsx", results.get("gl_matched")),
        ("GL_Third_Matched.xlsx", results.get("gl_third_matched")),
        ("Third_File_Matched.xlsx", results.get("third_matched")),
        ("Matched_Fidelity_GL_Summary.xlsx", results.get("fd_gl_matched_display")),
        ("Matched_GL_Third_File_Summary.xlsx", results.get("gl_third_matched_display")),
        ("Final_Reconciled_Statement.xlsx", results.get("reconciled_statement")),
    ]

def build_reconciliation_summary(fd, gl, fd_matched, gl_matched, gl_third_matched, third_matched, fd_unmatched, gl_unmatched, third_unmatched):
    return [
        {"label": "Total Bank Transactions", "value": len(fd)},
        {"label": "Total GL Entries", "value": len(gl)},
        {"label": "Total Report Entries", "value": len(third_unmatched) + len(third_matched)},
        {"label": "Matched Bank Statement and GL", "value": min(len(fd_matched), len(gl_matched))},
        {"label": "Matched GL and Report", "value": min(len(gl_third_matched), len(third_matched))},
        {"label": "Unmatched Bank", "value": len(fd_unmatched)},
        {"label": "Unmatched GL", "value": len(gl_unmatched)},
        {"label": "Unmatched Report", "value": len(third_unmatched)},
    ]


@login_required
def index(request):
    global FD_UNMATCHED, GL_UNMATCHED, THIRD_UNMATCHED, FD_MATCHED, GL_MATCHED, RECONCILED_STATEMENT, FD_GL_MATCHED_DISPLAY, GL_THIRD_MATCHED_DISPLAY
    unmatched_fd = unmatched_gl = unmatched_third = matched_fd_gl = matched_gl_third = reconciled_statement = None
    reconciliation_summary = None

    if request.method == 'POST':
        form = UploadFilesForm(request.POST, request.FILES)
        if form.is_valid():
            fd_file = request.FILES['fd_file']
            gl_file = request.FILES['gl_file']
            third_file = request.FILES['third_file']

            FD = remove_unnamed_columns(pd.read_excel(fd_file))
            GL = remove_unnamed_columns(pd.read_excel(gl_file))
            FD_UNMATCHED, GL_UNMATCHED, FD_MATCHED, GL_MATCHED = match_logic_with_matches(FD, GL)

            FD_UNMATCHED = FD_UNMATCHED.reset_index(drop=True)
            GL_UNMATCHED = GL_UNMATCHED.reset_index(drop=True)
            
            GL_UNMATCHED, THIRD_UNMATCHED, GL_THIRD_MATCHED, THIRD_MATCHED = apply_third_file_to_gl_unmatched_with_matches(
                third_file,
                GL_UNMATCHED,
            )
            RECONCILED_STATEMENT = build_reconciled_statement(
                GL,
                FD_UNMATCHED,
                GL_UNMATCHED,
                THIRD_UNMATCHED,
                include_section_titles=True,
            )

            unmatched_fd = dataframe_to_html(FD_UNMATCHED)
            unmatched_gl = dataframe_to_html(GL_UNMATCHED)
            unmatched_third = dataframe_to_html(THIRD_UNMATCHED)
            FD_GL_MATCHED_DISPLAY = build_fd_gl_matched_display(FD_MATCHED, GL_MATCHED)
            GL_THIRD_MATCHED_DISPLAY = build_gl_third_matched_display(GL_THIRD_MATCHED, THIRD_MATCHED)
            matched_fd_gl = dataframe_to_html(FD_GL_MATCHED_DISPLAY)
            matched_gl_third = dataframe_to_html(GL_THIRD_MATCHED_DISPLAY)
            reconciled_statement = dataframe_to_html(
                RECONCILED_STATEMENT,
                bold_empty_amount_narration=True,
            )
            reconciliation_summary = build_reconciliation_summary(
                FD,
                GL,
                FD_MATCHED,
                GL_MATCHED,
                GL_THIRD_MATCHED,
                THIRD_MATCHED,
                FD_UNMATCHED,
                GL_UNMATCHED,
                THIRD_UNMATCHED,
            )
            save_user_results(
                request.user,
                fd_unmatched=FD_UNMATCHED,
                gl_unmatched=GL_UNMATCHED,
                third_unmatched=THIRD_UNMATCHED,
                fd_matched=FD_MATCHED,
                gl_matched=GL_MATCHED,
                gl_third_matched=GL_THIRD_MATCHED,
                third_matched=THIRD_MATCHED,
                reconciled_statement=RECONCILED_STATEMENT,
                fd_gl_matched_display=FD_GL_MATCHED_DISPLAY,
                gl_third_matched_display=GL_THIRD_MATCHED_DISPLAY,
            )
            

    else:
        form = UploadFilesForm()

    return render(request, 'matcher/index.html', {
        'form': form,
        'profile': getattr(request.user, "profile", None),
        'unmatched_fd': unmatched_fd,
        'unmatched_gl': unmatched_gl,
        'unmatched_third': unmatched_third,
        'matched_fd_gl': matched_fd_gl,
        'matched_gl_third': matched_gl_third,
        'reconciled_statement': reconciled_statement,
        'reconciliation_summary': reconciliation_summary,
        'has_results': bool(USER_RESULTS.get(request.user.pk)),

    })


@login_required
def download_all_results(request):
    results = USER_RESULTS.get(request.user.pk, {})
    download_items = [
        (filename, dataframe)
        for filename, dataframe in build_download_items(results)
        if dataframe is not None
    ]

    if not download_items:
        return HttpResponse("No file to download")

    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, "w") as archive:
        for filename, dataframe in download_items:
            file_buffer = BytesIO()
            dataframe.to_excel(file_buffer, index=False, engine="openpyxl")
            archive.writestr(filename, file_buffer.getvalue())

    archive_buffer.seek(0)
    return HttpResponse(
        archive_buffer,
        content_type="application/zip",
        headers={'Content-Disposition': 'attachment; filename="Reconciliation_Results.zip"'},
    )


@login_required
def download_fd(request):
    return download_dataframe(get_user_result(request, "fd_unmatched"), "FD_Unmatched.xlsx")


@login_required
def download_gl(request):
    return download_dataframe(get_user_result(request, "gl_unmatched"), "GL_Unmatched.xlsx")

@login_required
def download_third(request):
    return download_dataframe(get_user_result(request, "third_unmatched"), "Third_Unmatched.xlsx")
                        

@login_required
def download_reconciled_statement(request):
    return download_dataframe(
        get_user_result(request, "reconciled_statement"),
        "Final_Reconciled_Statement.xlsx",
    )


@login_required
def download_matched_fd(request):
    return download_dataframe(get_user_result(request, "fd_matched"), "FD_Matched.xlsx")

@login_required
def download_matched_gl(request):
    return download_dataframe(get_user_result(request, "gl_matched"), "GL_Matched.xlsx")


@login_required
def download_matched_fd_gl(request):
    return download_dataframe(
        get_user_result(request, "fd_gl_matched_display"),
        "Matched_Fidelity_GL_Summary.xlsx",
    )


@login_required
def download_matched_gl_third(request):
    return download_dataframe(
        get_user_result(request, "gl_third_matched_display"),
        "Matched_GL_Third_File_Summary.xlsx",
    )
                        

# Create your views here.
