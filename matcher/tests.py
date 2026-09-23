from django.test import TestCase
from django.urls import reverse
from io import BytesIO
import pandas as pd
from zipfile import ZipFile

from django.contrib.auth import get_user_model

from .models import UserProfile
from .views import (
    amount_matches,
    apply_third_file_to_gl_unmatched,
    apply_third_file_to_gl_unmatched_with_matches,
    build_fd_gl_matched_display,
    build_gl_third_matched_display,
    build_reconciled_statement,
    match_logic,
    match_logic_with_matches,
    save_user_results,
)


class MatcherTests(TestCase):
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response["Location"])

    def test_signup_creates_user_profile(self):
        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "recon@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "account_type": UserProfile.ACCOUNT_TYPE_COMPANY,
                "full_name": "Ada Okafor",
                "company_name": "Ada Reconciliation Ltd",
                "phone_number": "08030000000",
                "address": "12 Ledger Street",
            },
        )

        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(email="recon@example.com")
        self.assertEqual(user.profile.full_name, "Ada Okafor")
        self.assertEqual(user.profile.company_name, "Ada Reconciliation Ltd")

    def test_download_all_results_returns_zip_for_signed_in_user(self):
        user = get_user_model().objects.create_user(
            username="recon@example.com",
            email="recon@example.com",
            password="StrongPass123!",
        )
        self.client.force_login(user)
        save_user_results(
            user,
            fd_unmatched=pd.DataFrame([{"Details": "Unmatched FD", "Amount": 100}]),
            gl_matched=pd.DataFrame([{"Narration": "Matched GL", "Amount": -100}]),
        )

        response = self.client.get(reverse("download_all_results"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")

        with ZipFile(BytesIO(response.content)) as archive:
            self.assertEqual(
                sorted(archive.namelist()),
                ["FD_Unmatched.xlsx", "GL_Matched.xlsx"],
            )

    def test_fd_gl_matched_display_pairs_narration_and_amounts(self):
        fidelity = pd.DataFrame([
            {"Details": "Known customer payment", "Amount": 100},
            {"Details": "Vendor refund", "Debit": 50},
        ])
        gl = pd.DataFrame([
            {"Narration": "Known customer payment", "Amount": -100},
            {"Narration": "Vendor refund", "Credit": 50},
        ])

        _, _, fd_matched, gl_matched = match_logic_with_matches(fidelity, gl)
        display = build_fd_gl_matched_display(fd_matched, gl_matched)

        self.assertEqual(
            display.columns.tolist(),
            ["Fidelity Narration", "Fidelity Amount", "GL Narration", "GL Amount"],
        )
        self.assertEqual(display["Fidelity Narration"].tolist(), ["Known customer payment", "Vendor refund"])
        self.assertEqual(display["Fidelity Amount"].tolist(), [100, 50])
        self.assertEqual(display["GL Narration"].tolist(), ["Known customer payment", "Vendor refund"])
        self.assertEqual(display["GL Amount"].tolist(), [-100, 50])

    def test_gl_third_matched_display_pairs_narration_and_amounts(self):
        gl_unmatched = pd.DataFrame([
            {"Narration": "Third document reference 456", "Amount": 200},
            {"Narration": "Still unresolved transaction", "Amount": 300},
        ])
        third_document = pd.DataFrame([
            {"Details": "Third document reference 456", "Amount": -200},
        ])
        third_file = BytesIO()
        third_document.to_excel(third_file, index=False, engine="openpyxl")
        third_file.seek(0)

        _, _, gl_matched, third_matched = apply_third_file_to_gl_unmatched_with_matches(
            third_file,
            gl_unmatched,
        )
        display = build_gl_third_matched_display(gl_matched, third_matched)

        self.assertEqual(
            display.columns.tolist(),
            ["GL Narration", "GL Amount", "Third File Narration", "Third File Amount"],
        )
        self.assertEqual(display["GL Narration"].tolist(), ["Third document reference 456"])
        self.assertEqual(display["GL Amount"].tolist(), [200])
        self.assertEqual(display["Third File Narration"].tolist(), ["Third document reference 456"])
        self.assertEqual(display["Third File Amount"].tolist(), [-200])

    def test_third_file_removes_entries_from_gl_unmatched(self):
        fidelity = pd.DataFrame([
            {"Details": "Known customer payment", "Amount": 100},
        ])
        gl = pd.DataFrame([
            {"Narration": "Known customer payment", "Amount": -100},
            {"Narration": "Third document reference 456", "Amount": 200},
            {"Narration": "Still unresolved transaction", "Amount": 300},
        ])
        third_document = pd.DataFrame([
            {"Details": "Third document reference 456", "Amount": -200},
        ])
        third_file = BytesIO()
        third_document.to_excel(third_file, index=False, engine="openpyxl")
        third_file.seek(0)

        _, gl_unmatched = match_logic(fidelity, gl)
        final_gl_unmatched, third_unmatched = apply_third_file_to_gl_unmatched(third_file, gl_unmatched)

        self.assertEqual(final_gl_unmatched["Narration"].tolist(), ["Still unresolved transaction"])
        self.assertEqual(third_unmatched["Details"].tolist(), [])

    def test_third_file_can_remove_gl_unmatched_with_debit_or_credit_amount(self):
        fidelity = pd.DataFrame([
            {"Details": "Known customer payment", "Amount": 100},
        ])
        gl = pd.DataFrame([
            {"Narration": "Known customer payment", "Amount": -100},
            {"Narration": "Third document reference 456", "Amount": -200},
            {"Narration": "Still unresolved transaction", "Amount": 300},
        ])
        third_document = pd.DataFrame([
            {"Narration": "Third document reference 456", "Debit": 0, "Credit": 200},
        ])
        third_file = BytesIO()
        third_document.to_excel(third_file, index=False, engine="openpyxl")
        third_file.seek(0)

        _, gl_unmatched = match_logic(fidelity, gl)
        final_gl_unmatched, third_unmatched = apply_third_file_to_gl_unmatched(third_file, gl_unmatched)

        self.assertEqual(final_gl_unmatched["Narration"].tolist(), ["Still unresolved transaction"])
        self.assertEqual(third_unmatched["Narration"].tolist(), [])

    def test_third_file_removes_exact_gl_row_without_amount(self):
        fidelity = pd.DataFrame([
            {"Details": "Known customer payment", "Amount": 100},
        ])
        gl = pd.DataFrame([
            {"Narration": "Known customer payment", "Amount": -100},
            {"Narration": "TRF frm Ogbanufe on 10-11-2022", "Amount": -9600},
            {"Narration": "Still unresolved transaction", "Amount": 300},
        ])
        third_document = pd.DataFrame([
            {"Narration": "TRF frm Ogbanufe on 10-11-2022"},
        ])
        third_file = BytesIO()
        third_document.to_excel(third_file, index=False, engine="openpyxl")
        third_file.seek(0)

        _, gl_unmatched = match_logic(fidelity, gl)
        final_gl_unmatched, third_unmatched = apply_third_file_to_gl_unmatched(third_file, gl_unmatched)

        self.assertEqual(final_gl_unmatched["Narration"].tolist(), ["Still unresolved transaction"])
        self.assertEqual(third_unmatched["Narration"].tolist(), [])

    def test_third_file_removes_row_with_spaced_and_alternate_amount_columns(self):
        fidelity = pd.DataFrame([
            {"Details": "Known customer payment", "Amount": 100},
        ])
        gl = pd.DataFrame([
            {"Narration": "Known customer payment", "Amount ": -100},
            {"Narration": "Third document reference 456", "Amount ": -200},
            {"Narration": "Still unresolved transaction", "Amount ": 300},
        ])
        third_document = pd.DataFrame([
            {"Description": "Third document reference 456", "Credit Amount": 200},
        ])
        third_file = BytesIO()
        third_document.to_excel(third_file, index=False, engine="openpyxl")
        third_file.seek(0)

        _, gl_unmatched = match_logic(fidelity, gl)
        final_gl_unmatched, third_unmatched = apply_third_file_to_gl_unmatched(third_file, gl_unmatched)

        self.assertEqual(final_gl_unmatched["Narration"].tolist(), ["Still unresolved transaction"])
        self.assertEqual(third_unmatched["Description"].tolist(), [])

    def test_third_file_removes_every_matching_gl_unmatched_row(self):
        fidelity = pd.DataFrame([
            {"Details": "Known customer payment", "Amount": 100},
        ])
        gl = pd.DataFrame([
            {"Narration": "Known customer payment", "Amount": -100},
            {"Narration": "Third document reference 456", "Amount": 200},
            {"Narration": "Third document reference 456", "Amount": 200},
            {"Narration": "Still unresolved transaction", "Amount": 300},
        ])
        third_document = pd.DataFrame([
            {"Details": "Third document reference 456", "Amount": -200},
        ])
        third_file = BytesIO()
        third_document.to_excel(third_file, index=False, engine="openpyxl")
        third_file.seek(0)

        _, gl_unmatched = match_logic(fidelity, gl)
        final_gl_unmatched, third_unmatched = apply_third_file_to_gl_unmatched(third_file, gl_unmatched)

        self.assertEqual(final_gl_unmatched["Narration"].tolist(), ["Still unresolved transaction"])
        self.assertEqual(third_unmatched["Details"].tolist(), [])

    def test_third_file_unmatched_records_are_returned(self):
        fidelity = pd.DataFrame([
            {"Details": "Known customer payment", "Amount": 100},
        ])
        gl = pd.DataFrame([
            {"Narration": "Known customer payment", "Amount": -100},
            {"Narration": "Third document reference 456", "Amount": 200},
            {"Narration": "Still unresolved transaction", "Amount": 300},
        ])
        third_document = pd.DataFrame([
            {"Details": "Third document reference 456", "Amount": -200},
            {"Details": "Third file only transaction", "Amount": 400},
        ])
        third_file = BytesIO()
        third_document.to_excel(third_file, index=False, engine="openpyxl")
        third_file.seek(0)

        _, gl_unmatched = match_logic(fidelity, gl)
        final_gl_unmatched, third_unmatched = apply_third_file_to_gl_unmatched(third_file, gl_unmatched)

        self.assertEqual(final_gl_unmatched["Narration"].tolist(), ["Still unresolved transaction"])
        self.assertEqual(third_unmatched["Details"].tolist(), ["Third file only transaction"])

    def test_third_file_removes_matches_with_different_text_column_name(self):
        fidelity = pd.DataFrame([
            {"Details": "Known customer payment", "Amount": 100},
        ])
        gl = pd.DataFrame([
            {"Narration": "Known customer payment", "Amount": -100},
            {"Narration": "Third document reference 456", "Amount": 200},
            {"Narration": "Still unresolved transaction", "Amount": 300},
        ])
        third_document = pd.DataFrame([
            {"Transaction Description": "Third document reference 456", "Amount": -200},
        ])
        third_file = BytesIO()
        third_document.to_excel(third_file, index=False, engine="openpyxl")
        third_file.seek(0)

        _, gl_unmatched = match_logic(fidelity, gl)
        final_gl_unmatched, third_unmatched = apply_third_file_to_gl_unmatched(third_file, gl_unmatched)

        self.assertEqual(final_gl_unmatched["Narration"].tolist(), ["Still unresolved transaction"])
        self.assertEqual(third_unmatched["Transaction Description"].tolist(), [])

    def test_third_file_keeps_rows_that_only_share_amount(self):
        fidelity = pd.DataFrame([
            {"Details": "Known customer payment", "Amount": 100},
        ])
        gl = pd.DataFrame([
            {"Narration": "Known customer payment", "Amount": -100},
            {"Narration": "Third document reference 456", "Amount": 200},
        ])
        third_document = pd.DataFrame([
            {"Details": "Different third file transaction", "Amount": 200},
        ])
        third_file = BytesIO()
        third_document.to_excel(third_file, index=False, engine="openpyxl")
        third_file.seek(0)

        _, gl_unmatched = match_logic(fidelity, gl)
        final_gl_unmatched, third_unmatched = apply_third_file_to_gl_unmatched(third_file, gl_unmatched)

        self.assertEqual(final_gl_unmatched["Narration"].tolist(), ["Third document reference 456"])
        self.assertEqual(third_unmatched["Details"].tolist(), ["Different third file transaction"])

    def test_amount_matches_requires_opposite_sides(self):
        self.assertTrue(
            amount_matches(
                pd.Series({"Narration": "Credit side", "Credit": 250}),
                pd.Series({"Narration": "Debit side", "Debit": 250}),
            )
        )
        self.assertTrue(
            amount_matches(
                pd.Series({"Narration": "Debit side", "Debit": 250}),
                pd.Series({"Narration": "Credit side", "Credit": 250}),
            )
        )
        self.assertFalse(
            amount_matches(
                pd.Series({"Narration": "Credit side", "Credit": 250}),
                pd.Series({"Narration": "Credit side", "Credit": 250}),
            )
        )
        self.assertFalse(
            amount_matches(
                pd.Series({"Narration": "Debit side", "Debit": 250}),
                pd.Series({"Narration": "Debit side", "Debit": 250}),
            )
        )

    def test_reconciled_statement_adds_credits_and_subtracts_debits(self):
        gl = pd.DataFrame([
            {"Date": "2026-01-01", "Narration": "Opening", "Balance": 900},
            {"Date": "2026-01-02", "Narration": "Closing", "Balance": 1000},
        ])
        fd_unmatched = pd.DataFrame([
            {"Date": "2026-01-03", "Details": "FD credit", "Amount": 100},
            {"Date": "2026-01-04", "Details": "FD debit", "Amount": -20},
        ])
        gl_unmatched = pd.DataFrame([
            {"Date": "2026-01-05", "Narration": "GL credit", "Credit": 50},
            {"Date": "2026-01-06", "Narration": "GL debit", "Debit": 25},
        ])
        third_unmatched = pd.DataFrame([
            {"Date": "2026-01-07", "Details": "Third credit", "Amount": 30},
            {"Date": "2026-01-08", "Details": "Third debit", "Amount": -10},
        ])

        statement = build_reconciled_statement(
            gl,
            fd_unmatched,
            gl_unmatched,
            third_unmatched,
        )

        self.assertEqual(
            statement["Narration"].tolist(),
            [
                "Add",
                "FD credit",
                "GL credit",
                "Third credit",
                "Total",
                "Less",
                "FD debit",
                "GL debit",
                "Third debit",
                "Final Balance",
            ],
        )
        self.assertEqual(statement[""].iloc[0], 1000)
        self.assertEqual(statement[""].iloc[4], 1180)
        self.assertEqual(statement[""].iloc[9], 1125)
