"""What the LLM must return for spec 1.2. Every amount, percentage and date is a STRING exactly
as printed: converting text to numbers is deterministic code's job (parsing.py), not the model's."""

from pydantic import BaseModel, Field


class ExtractedAddress(BaseModel):
    name: str = Field(description="First line of the address block (company or recipient name)")
    street: str = Field(description="Street and house number")
    zip_code: str
    city: str
    country: str
    address_specification: str | None = Field(None, description="Extra address line, only if printed")
    district: str | None = Field(None, description="District, only if printed")


class ExtractedItem(BaseModel):
    position: int = Field(description="Row number as printed, 1-based")
    sku: str = Field(description="Item SKU / article number exactly as printed")
    description: str
    quantity: str
    unit_net_price: str = Field(description="Unit net price as printed, without currency")
    discount_percent: str = Field(description="Line discount as printed, e.g. '10%' or '0%'")
    vat_percent: str = Field(description="VAT rate as printed, e.g. '19%'")
    line_net_total: str = Field(description="Line net total as printed, without currency")


class ExtractedOrder(BaseModel):
    external_reference: str = Field(description="External / customer order reference")
    order_date: str = Field(description="Order date exactly as printed")
    date_format_note: str | None = Field(
        None, description="Date format stated on the document (e.g. 'YYYY-MM-DD'), if any"
    )
    currency: str
    customer_id: str | None = Field(None, description="Customer ID printed on the document, if any")
    company: str = Field(description="Customer company name ('' if the customer is a person)")
    contact_first_name: str
    contact_last_name: str
    salutation: str | None = Field(None, description="Salutation (Mr/Ms/...), only if printed")
    customer_alias: str = Field(description="Customer alias / short name ('' if not printed)")
    email: str
    phone: str
    billing_address: ExtractedAddress
    delivery_address: ExtractedAddress = Field(
        description="Delivery address; repeat the billing address if only one address is printed"
    )
    payment_method: str = Field(description="Payment method exactly as printed, e.g. 'Bank Transfer'")
    paid_status: str = Field(description="Paid status exactly as printed, e.g. 'PAID' or 'UNPAID'")
    payment_date: str | None = Field(None, description="Payment date as printed, only if printed")
    items: list[ExtractedItem]
    order_discount_percent: str | None = Field(None, description="Order-level discount, only if printed")
    shipping_net: str | None = Field(None, description="Order-level shipping cost, only if printed")
    net_total: str
    vat_total: str
    gross_total: str
