"""Google Sheets API client wrapper."""

import logging
import time
import random
from typing import List, Dict, Any, Optional
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

logger = logging.getLogger(__name__)


class SheetsClient:
    """Google Sheets API wrapper with error handling and retry logic."""

    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    def __init__(self, credentials_path: Any, sheet_id: str):
        """Initialize the Sheets client.

        Args:
            credentials_path: Path to JSON file OR a dictionary containing service account credentials.
            sheet_id: Google Sheets document ID.
        """
        if not sheet_id or sheet_id.strip() == "":
            raise ValueError("❌ Critical Error: Google Sheet ID is empty or not configured correctly.")
            
        self.sheet_id = sheet_id.strip()
        self.service = self._authenticate(credentials_path)

    def _authenticate(self, credentials_path: Any):
        """Authenticate with Google Sheets API supporting both files and dicts."""
        try:
            # Suppress discovery cache warning
            import logging
            logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
            
            if isinstance(credentials_path, dict):
                logger.info("Authenticating using credentials dictionary/secrets.")
                creds = Credentials.from_service_account_info(
                    credentials_path, scopes=self.SCOPES
                )
            else:
                logger.info(f"Authenticating using credentials file: {credentials_path}")
                creds = Credentials.from_service_account_file(
                    credentials_path, scopes=self.SCOPES
                )
            return build("sheets", "v4", credentials=creds, cache_discovery=False)
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise

    def _execute_with_retry(self, request, max_retries=3):
        """Execute Google API request with exponential backoff."""
        for attempt in range(max_retries):
            try:
                return request.execute()
            except HttpError as e:
                if e.resp.status in [429, 500, 503]:
                    wait_time = (2 ** attempt) + random.random()
                    logger.warning(f"Rate limited. Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                else:
                    raise
        return request.execute()

    def read_range(self, range_name: str) -> List[List[str]]:
        """Read data from a specific range.

        Args:
            range_name: A1 notation range (e.g., 'Sheet1!A1:J100').

        Returns:
            List of rows, where each row is a list of cell values.
        """
        try:
            request = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id, range=range_name
            )
            result = self._execute_with_retry(request)
            return result.get("values", [])
        except HttpError as e:
            logger.error(f"Error reading range {range_name}: {e}")
            raise

    def write_range(
        self, range_name: str, values: List[List[Any]], value_input_option: str = "RAW"
    ) -> bool:
        """Write data to a specific range.

        Args:
            range_name: A1 notation range.
            values: 2D list of values to write.
            value_input_option: How to interpret input ('RAW' or 'USER_ENTERED').

        Returns:
            True if successful.
        """
        try:
            body = {"values": values}
            request = self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                body=body,
                responseValueRenderOption="FORMATTED_VALUE" 
            )
            self._execute_with_retry(request)
            logger.info(f"Successfully wrote to {range_name}")
            return True
        except HttpError as e:
            logger.error(f"Error writing to {range_name}: {e}")
            raise

    def clear_range(self, range_name: str) -> bool:
        """Clear values from a specific range.

        Args:
            range_name: A1 notation range.

        Returns:
            True if successful.
        """
        try:
            request = self.service.spreadsheets().values().clear(
                spreadsheetId=self.sheet_id,
                range=range_name,
                body={}
            )
            self._execute_with_retry(request)
            logger.info(f"Successfully cleared {range_name}")
            return True
        except HttpError as e:
            logger.error(f"Error clearing {range_name}: {e}")
            raise

    def append_row(
        self, range_name: str, values: List[Any], value_input_option: str = "USER_ENTERED"
    ) -> int:
        """Append a row to the end of the range.

        Args:
            range_name: A1 notation range (e.g., 'Bookings!A:J').
            values: Single row of values.
            value_input_option: How to interpret input.

        Returns:
            Row number where data was appended.
        """
        try:
            body = {"values": [values]}
            request = (
                self.service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=self.sheet_id,
                    range=range_name,
                    valueInputOption=value_input_option,
                    body=body,
                )
            )
            result = self._execute_with_retry(request)
            updates = result.get("updates", {})
            updated_range = updates.get("updatedRange", "")
            # Extract row number from range like 'Bookings!A5:J5'
            row_num = int(updated_range.split("!")[-1].split(":")[0][1:])
            logger.info(f"Appended row {row_num}")
            return row_num
        except HttpError as e:
            logger.error(f"Error appending row: {e}")
            raise

    def update_cell(
        self, sheet_name: str, row: int, col: int, value: Any
    ) -> bool:
        """Update a single cell.

        Args:
            sheet_name: Name of the sheet.
            row: Row number (1-indexed).
            col: Column number (1-indexed, A=1, B=2, etc.).
            value: Value to write.

        Returns:
            True if successful.
        """
        col_letter = chr(64 + col)  # Convert 1->A, 2->B, etc.
        range_name = f"{sheet_name}!{col_letter}{row}"
        return self.write_range(range_name, [[value]], "USER_ENTERED")

    def get_sheet_id(self, sheet_name: str) -> Optional[int]:
        """Get the numerical ID for a sheet by its title."""
        try:
            spreadsheet = self.service.spreadsheets().get(spreadsheetId=self.sheet_id).execute()
            for sheet in spreadsheet.get("sheets", []):
                if sheet["properties"]["title"] == sheet_name:
                    return sheet["properties"]["sheetId"]
            return None
        except HttpError as e:
            logger.error(f"Error getting sheet ID: {e}")
            raise

    def delete_sheet_by_name(self, sheet_name: str) -> bool:
        """Delete a sheet tab by its name."""
        sheet_id = self.get_sheet_id(sheet_name)
        if sheet_id is not None:
            logger.info(f"Deleting default sheet: {sheet_name}")
            return self.batch_update([{"deleteSheet": {"sheetId": sheet_id}}])
        return False

    def set_dropdown(self, sheet_name: str, range_name: str, options: List[str]):
        """Create a drop-down menu in the specified range."""
        sheet_id = self.get_sheet_id(sheet_name)
        if sheet_id is None:
            return

        # Parse range (e.g., 'A2:A100')
        start_col = ord(range_name[0].upper()) - 65
        start_row = int(''.join(filter(str.isdigit, range_name.split(':')[0]))) - 1
        end_row = int(''.join(filter(str.isdigit, range_name.split(':')[1])))

        request = {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row,
                    "endRowIndex": end_row,
                    "startColumnIndex": start_col,
                    "endColumnIndex": start_col + 1
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": opt} for opt in options]
                    },
                    "showCustomUi": True,
                    "strict": True
                }
            }
        }
        return self.batch_update([request])

    def get_sheet_names(self) -> List[str]:
        """Get a list of all sheet names in the spreadsheet."""
        try:
            request = self.service.spreadsheets().get(spreadsheetId=self.sheet_id)
            spreadsheet = self._execute_with_retry(request)
            return [sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])]
        except HttpError as e:
            logger.error(f"Error getting sheet names: {e}")
            raise

    def ensure_sheets_exist(self, sheet_names: List[str]) -> bool:
        """Check if sheets exist and create them if missing."""
        existing_sheets = self.get_sheet_names()
        requests = []
        
        for name in sheet_names:
            if name not in existing_sheets:
                logger.info(f"Adding missing sheet: {name}")
                requests.append({
                    "addSheet": {
                        "properties": {
                            "title": name
                        }
                    }
                })
        
        if requests:
            return self.batch_update(requests)
        return True

    def batch_update(self, updates: List[Dict[str, Any]]) -> bool:
        """Perform batch updates for efficiency.

        Args:
            updates: List of update requests.

        Returns:
            True if successful.
        """
        try:
            body = {"requests": updates}
            request = self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id, body=body
            )
            self._execute_with_retry(request)
            logger.info(f"Batch update completed with {len(updates)} requests")
            return True
        except HttpError as e:
            logger.error(f"Batch update failed: {e}")
            raise

    def set_row_height(self, sheet_name: str, start_row: int, end_row: int, height: int):
        """Set height of rows for better mobile touch experience."""
        sheet_id = self.get_sheet_id(sheet_name)
        if sheet_id is None: return
        
        request = {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": start_row,
                    "endIndex": end_row
                },
                "properties": {
                    "pixelSize": height
                },
                "fields": "pixelSize"
            }
        }
        return self.batch_update([request])

    def set_column_width(self, sheet_name: str, start_col: int, end_col: int, width: int):
        """Set width of columns for better visualization."""
        sheet_id = self.get_sheet_id(sheet_name)
        if sheet_id is None: return
        
        request = {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": start_col,
                    "endIndex": end_col
                },
                "properties": {
                    "pixelSize": width
                },
                "fields": "pixelSize"
            }
        }
        return self.batch_update([request])

    def format_cells(self, sheet_name: str, range_name: str, 
                     bg_color: Dict[str, float] = None, 
                     text_color: Dict[str, float] = None, 
                     bold: bool = False, 
                     font_size: int = 10,
                     horizontal_alignment: str = "LEFT"):
        """Apply formatting to a range of cells using precise field masks."""
        sheet_id = self.get_sheet_id(sheet_name)
        if sheet_id is None: return

        # Simple range parser (A1:B10)
        import re
        match = re.match(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", range_name.upper())
        if not match: return
        
        start_col_str, start_row_str, end_col_str, end_row_str = match.groups()
        
        def col_to_index(col):
            index = 0
            for char in col: index = index * 26 + (ord(char) - ord('A') + 1)
            return index - 1

        start_col = col_to_index(start_col_str)
        end_col = col_to_index(end_col_str) + 1
        start_row = int(start_row_str) - 1
        end_row = int(end_row_str)

        # 1. Start with base fields
        fields_list = [
            "userEnteredFormat.textFormat.bold",
            "userEnteredFormat.textFormat.fontSize",
            "userEnteredFormat.horizontalAlignment"
        ]
        
        # 2. Base cell data
        cell_data = {
            "userEnteredFormat": {
                "textFormat": {
                    "bold": bold,
                    "fontSize": font_size
                },
                "horizontalAlignment": horizontal_alignment
            }
        }

        # 3. Dynamic overrides
        if bg_color:
            cell_data["userEnteredFormat"]["backgroundColor"] = bg_color
            fields_list.append("userEnteredFormat.backgroundColor")
            
        if text_color:
            cell_data["userEnteredFormat"]["textFormat"]["foregroundColor"] = text_color
            fields_list.append("userEnteredFormat.textFormat.foregroundColor")

        request = {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row,
                    "endRowIndex": end_row,
                    "startColumnIndex": start_col,
                    "endColumnIndex": end_col
                },
                "cell": cell_data,
                "fields": ",".join(fields_list)
            }
        }
        
        return self.batch_update([request])

    def add_conditional_formatting(self, sheet_name: str, range_name: str, rules: List[Dict]):
        """Add conditional formatting rules to a range."""
        sheet_id = self.get_sheet_id(sheet_name)
        if sheet_id is None: return

        import re
        match = re.match(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", range_name.upper())
        if not match: return
        start_col_str, start_row_str, end_col_str, end_row_str = match.groups()
        
        def col_to_index(col):
            index = 0
            for char in col: index = index * 26 + (ord(char) - ord('A') + 1)
            return index - 1

        start_col = col_to_index(start_col_str)
        end_col = col_to_index(end_col_str) + 1
        start_row = int(start_row_str) - 1
        end_row = int(end_row_str)

        requests = []
        for rule in rules:
            formatted_rule = {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": sheet_id,
                            "startRowIndex": start_row,
                            "endRowIndex": end_row,
                            "startColumnIndex": start_col,
                            "endColumnIndex": end_col
                        }],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_CONTAINS",
                                "values": [{"userEnteredValue": rule["text"]}]
                            },
                            "format": {
                                "backgroundColor": rule["bg_color"],
                                "textFormat": {"foregroundColor": rule.get("text_color", {"red": 0, "green": 0, "blue": 0}), "bold": True}
                            }
                        }
                    },
                    "index": 0
                }
            }
            requests.append(formatted_rule)
        
        return self.batch_update(requests)
