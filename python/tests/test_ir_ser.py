import unittest
from ir import *
from ir_ser_txt import *

class TestStatementSeqSerialization(unittest.TestCase):
    def test_empty_sequence(self):
        empty_seq = StatementSeq(stmts=[])
        self.assertEqual(serialize_statement_seq(empty_seq), "")

    def test_deserialize_complex_statement(self):
        stmt_txt = "8 5 x 6 y = add v1 a b c"
        stmt_ir = deserialize_statement(stmt_txt)
        stmt_txt2 = serialize_statement(stmt_ir)
        self.assertEqual(stmt_txt, stmt_txt2)

    def test_stmt_seq(self):
        text = '\n'.join([
            '4 1 a = env load;',
            '2c 3 b = env store x y z;',
            '2c 3 b = env store x y z;',
        ]) + '\n'
        ir = deserialize_statement_seq(text)
        text2 = serialize_statement_seq(ir)
        self.assertEqual(text2, text)

if __name__ == '__main__':
    unittest.main()
