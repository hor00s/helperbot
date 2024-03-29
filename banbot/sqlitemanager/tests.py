import unittest
from pathlib import Path
from .manager import (
    Datatype,
    Table,
    Row,
    DB,
)


class TestManager(unittest.TestCase):
    def setUp(self) -> None:
        path = Path(__file__).parent / "test.sqlite"
        print(path)
        self.db = DB(str(path))
        self.table_name = "table_name"
        self.db.create_table(self.table_name, name=Datatype.STR, age=Datatype.INT)
        return super().setUp()

    def tearDown(self) -> None:
        table = self.db.get_table(self.table_name)
        table.drop()
        return super().tearDown()

    def test_save_and_delete(self) -> None:
        name, age = "giannis", 15
        table = self.db.get_table(self.table_name)
        row = table.make_row(name=name, age=age)
        row.save()
        table = self.db.get_table(self.table_name)
        row = table.get_row(name=name, age=age)  # type: ignore
        row.delete()
        table = self.db.get_table(self.table_name)
        self.assertNotIn(row, table)  # type: ignore

    def test_edit(self) -> None:
        name, age = "giannis", 15
        table = self.db.get_table(self.table_name)
        row = table.make_row(name=name, age=age)
        row.save()
        table = self.db.get_table(self.table_name)
        row = table.get_row(name=name, age=age)  # type: ignore
        new_name = "john"
        row.name = new_name  # type: ignore
        row.edit()
        table_after = self.db.get_table(self.table_name)
        row_after = table_after.get_row(name=new_name, age=age)
        self.assertEqual(row_after.name, new_name)  # type: ignore
        self.assertEqual(row_after.age, age)  # type: ignore
        self.assertEqual(row.pk, row_after.pk)  # type: ignore

    def test_get_table(self) -> None:
        table = self.db.get_table(self.table_name)
        self.assertIsInstance(table, Table)

        default = 5
        table = self.db.get_table("not_existing", default)  # type: ignore
        self.assertEqual(type(default), type(table))
