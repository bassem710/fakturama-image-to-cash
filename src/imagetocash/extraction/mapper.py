"""ExtractedOrder (strings as printed) -> OrderDocument (typed, Decimal, dates)."""

from collections.abc import Sequence
from decimal import Decimal

from imagetocash.domain.models import Address, Debtor, LineItem, OrderDocument, PaymentInfo, SourceTotals
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.extraction.parsing import (
    DEFAULT_DATE_FORMATS,
    ParseError,
    parse_amount,
    parse_date,
    parse_percent,
)
from imagetocash.extraction.schema import ExtractedAddress, ExtractedOrder


def _address(source: ExtractedAddress) -> Address:
    return Address(
        name=source.name.strip(),
        street=source.street.strip(),
        zip_code=source.zip_code.strip(),
        city=source.city.strip(),
        country=source.country.strip(),
        address_specification=(source.address_specification or "").strip() or None,
        district=(source.district or "").strip() or None,
    )


def to_order_document(extracted: ExtractedOrder, date_formats: Sequence[str] = DEFAULT_DATE_FORMATS) -> OrderDocument:
    try:
        items = tuple(
            LineItem(
                position=item.position,
                sku=item.sku.strip(),
                description=item.description.strip(),
                quantity=parse_amount(item.quantity),
                unit_net_price=parse_amount(item.unit_net_price),
                vat_percent=parse_percent(item.vat_percent),
                discount_percent=parse_percent(item.discount_percent),
                source_line_total=parse_amount(item.line_net_total),
            )
            for item in sorted(extracted.items, key=lambda i: i.position)
        )
        payment_date = parse_date(extracted.payment_date, date_formats) if extracted.payment_date else None
        return OrderDocument(
            order_date=parse_date(extracted.order_date, date_formats),
            external_reference=extracted.external_reference.strip(),
            currency=extracted.currency.strip(),
            debtor=Debtor(
                company=extracted.company.strip(),
                first_name=extracted.contact_first_name.strip(),
                last_name=extracted.contact_last_name.strip(),
                alias=extracted.customer_alias.strip(),
                email=extracted.email.strip(),
                telephone=extracted.phone.strip(),
                billing_address=_address(extracted.billing_address),
                delivery_address=_address(extracted.delivery_address),
                salutation=(extracted.salutation or "").strip() or None,
                source_customer_id=extracted.customer_id,
            ),
            payment=PaymentInfo(
                method=extracted.payment_method.strip(),
                paid_status=extracted.paid_status.strip(),
                payment_date=payment_date,
            ),
            items=items,
            totals=SourceTotals(
                net=parse_amount(extracted.net_total),
                vat=parse_amount(extracted.vat_total),
                gross=parse_amount(extracted.gross_total),
            ),
            order_discount_percent=parse_percent(extracted.order_discount_percent),
            shipping_net=parse_amount(extracted.shipping_net) if extracted.shipping_net else Decimal(0),
        )
    except ParseError as error:
        raise ManualReviewRequired("1.1", ReviewReason.EXTRACTION_INVALID, str(error)) from error
