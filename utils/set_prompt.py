from get_money_agent.constants import SYSTEM_PROMPT


def set_prompt(
    customer_name: str,
    company_name: str,
    desired_resolution: str,
    account_number: str,
    product_or_service: str,
    issue_description: str,
    proof: str
):
    """
    Sets up the prompt with all required customer and issue information.

    Args:
        customer_name: Name of the customer
        company_name: Name of the company being called
        desired_resolution: What the customer wants (e.g., "full refund of $120")
        account_number: Customer's account or order number
        product_or_service: The service or product in question
        issue_description: Summary of the customer's issue
        proof: Evidence available to support the claim

    Returns:
        Formatted system prompt with all customer details
    """
    call_info = {
        "CustomerName": customer_name,
        "CompanyName": company_name,
        "DesiredResolution": desired_resolution,
        "AccountNumber": account_number,
        "ProductOrService": product_or_service,
        "IssueDescription": issue_description,
        "Proof": proof
    }
    return SYSTEM_PROMPT.format_map(call_info)
