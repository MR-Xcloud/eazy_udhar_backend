TAX_TYPE_CGST_SGST = 'cgst_sgst'
TAX_TYPE_IGST = 'igst'

# Supplier (Inwizy Global Ventures LLP) GSTIN state code — first 2 digits of
# the GSTIN. 06 = Haryana. Used to decide intra-state (CGST+SGST) vs
# inter-state (IGST) supply for subscription invoices.
SUPPLIER_STATE_CODE = '06'

# GST state codes → place-of-supply names, as the CRM finance module expects
# them on an ingested invoice.
STATE_NAMES = {
    '01': 'Jammu and Kashmir',      '02': 'Himachal Pradesh',
    '03': 'Punjab',                 '04': 'Chandigarh',
    '05': 'Uttarakhand',            '06': 'Haryana',
    '07': 'Delhi',                  '08': 'Rajasthan',
    '09': 'Uttar Pradesh',          '10': 'Bihar',
    '11': 'Sikkim',                 '12': 'Arunachal Pradesh',
    '13': 'Nagaland',               '14': 'Manipur',
    '15': 'Mizoram',                '16': 'Tripura',
    '17': 'Meghalaya',              '18': 'Assam',
    '19': 'West Bengal',            '20': 'Jharkhand',
    '21': 'Odisha',                 '22': 'Chhattisgarh',
    '23': 'Madhya Pradesh',         '24': 'Gujarat',
    '26': 'Dadra and Nagar Haveli and Daman and Diu',
    '27': 'Maharashtra',            '29': 'Karnataka',
    '30': 'Goa',                    '31': 'Lakshadweep',
    '32': 'Kerala',                 '33': 'Tamil Nadu',
    '34': 'Puducherry',             '35': 'Andaman and Nicobar Islands',
    '36': 'Telangana',              '37': 'Andhra Pradesh',
    '38': 'Ladakh',                 '97': 'Other Territory',
}


def state_code_from_gstin(gst_number: str) -> str:
    """First two digits of a well-formed GSTIN, or '' when we can't trust it.
    Same validity test as determine_tax_type(), so the two never disagree."""
    gst_number = (gst_number or '').strip().upper()
    state_code = gst_number[:2]
    if len(gst_number) < 15 or not state_code.isdigit():
        return ''
    return state_code


def state_name(state_code: str) -> str:
    return STATE_NAMES.get((state_code or '').strip(), '')


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
