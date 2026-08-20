TAX_TYPE_CGST_SGST = 'cgst_sgst'
TAX_TYPE_IGST = 'igst'

# Supplier (Inwizy Global Ventures LLP) GSTIN state code — first 2 digits of
# the GSTIN. 06 = Haryana. Used to decide intra-state (CGST+SGST) vs
# inter-state (IGST) supply for subscription invoices.
SUPPLIER_STATE_CODE = '06'


def determine_tax_type(customer_gst_number: str) -> str:
    """Place-of-supply default for a customer who may not have given us their
    state: if we don't have a valid GSTIN to read a state code from, treat the
    place of supply as the supplier's own location (Section 12(2) IGST Act
    proviso) — i.e. intra-state, CGST+SGST. Only switch to IGST once the
    GSTIN's state code proves the customer is in a different state."""
    gst_number = (customer_gst_number or '').strip().upper()
    state_code = gst_number[:2]
    if len(gst_number) < 15 or not state_code.isdigit():
        return TAX_TYPE_CGST_SGST
    return TAX_TYPE_IGST if state_code != SUPPLIER_STATE_CODE else TAX_TYPE_CGST_SGST
