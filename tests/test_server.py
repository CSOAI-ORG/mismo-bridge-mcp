import sys,os
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

X="<DEAL><LOAN><TERMS><BaseLoanAmount>300000</BaseLoanAmount></TERMS></LOAN><BORROWER><FirstName>A</FirstName></BORROWER></DEAL>"
def test_parse():
    p=server.parse_mismo(X); assert p.loan_amount=="300000"; assert p.has_borrower
def test_validate():
    assert server.validate_mismo(X).valid
def test_govern():
    assert any("ECOA" in f for f in server.govern_mortgage(X).frameworks)
