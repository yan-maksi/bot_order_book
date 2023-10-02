import logging
import threading
import queue


class TableLogger:
    def __init__(self, filename, columns):
        self.columns = columns
        self.row_data = {col: '' for col in self.columns}
        self._initialize_logger(filename)
        self._start_log_writer_thread()

    def _initialize_logger(self, filename):
        self.logger = logging.getLogger('table_logger')
        self.logger.setLevel(logging.INFO)
        handler = logging.FileHandler(filename)
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)
        self.logger.info('\t'.join(self.columns))

    def _start_log_writer_thread(self):
        self.log_queue = queue.Queue()
        log_writer_thread = threading.Thread(target=self._write_log_from_queue, daemon=True)
        log_writer_thread.start()

    def log_value(self, column, value=None):
        values_to_log = {column: value} if value is not None else column
        self._validate_and_update_row(values_to_log)
        self._try_log_row()

    def _validate_and_update_row(self, values):
        for col, val in values.items():
            if col in self.columns:
                self.row_data[col] = str(val)

    def _try_log_row(self):
        if all(self.row_data[col] != '' for col in self.columns):
            self.log_queue.put('\t'.join(self.row_data[col] for col in self.columns))
            self.row_data = {col: '' for col in self.columns}

    def _write_log_from_queue(self):
        while True:
            log_message = self.log_queue.get()
            self.logger.info(log_message)
            self.log_queue.task_done()

# Example usage:
# logger = TableLogger()
# logger.log_value("entry_price", 123.45)
# logger.log_value({
#     "stop_loss_price": [120.0, 121.0],
#     "opening_side": "buy"})