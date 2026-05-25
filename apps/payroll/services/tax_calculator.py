from decimal import Decimal, ROUND_HALF_UP
from typing import Dict


class KenyanTaxCalculator:
    """
    Kenya statutory deductions calculator (2024 rates)
    """

    # PAYE Tax Bands (Monthly)
    PAYE_BANDS = [
        (Decimal('24000'), Decimal('0.10')),
        (Decimal('8333'), Decimal('0.25')),
        (Decimal('467667'), Decimal('0.30')),
        (Decimal('300000'), Decimal('0.325')),
        (None, Decimal('0.35')),  # Above 800,000
    ]

    PERSONAL_RELIEF = Decimal('2400')  # Monthly

    # NSSF (Tier I & II combined)
    NSSF_RATE = Decimal('0.06')
    NSSF_UPPER_LIMIT = Decimal('18000')  # Max pensionable earnings

    # NHIF Bands
    NHIF_BANDS = [
        (Decimal('5999'), Decimal('150')),
        (Decimal('7999'), Decimal('300')),
        (Decimal('11999'), Decimal('400')),
        (Decimal('14999'), Decimal('500')),
        (Decimal('19999'), Decimal('600')),
        (Decimal('24999'), Decimal('750')),
        (Decimal('29999'), Decimal('850')),
        (Decimal('34999'), Decimal('900')),
        (Decimal('39999'), Decimal('950')),
        (Decimal('44999'), Decimal('1000')),
        (Decimal('49999'), Decimal('1100')),
        (Decimal('59999'), Decimal('1200')),
        (Decimal('69999'), Decimal('1300')),
        (Decimal('79999'), Decimal('1400')),
        (Decimal('89999'), Decimal('1500')),
        (Decimal('99999'), Decimal('1600')),
        (None, Decimal('1700')),  # 100,000+
    ]

    # Housing Levy
    HOUSING_LEVY_RATE = Decimal('0.015')  # 1.5% each for employee and employer

    def calculate_nssf(self, gross_pay: Decimal) -> Dict[str, Decimal]:
        """Calculate NSSF contributions (employee & employer)"""
        pensionable = min(gross_pay, self.NSSF_UPPER_LIMIT)
        contribution = (pensionable * self.NSSF_RATE).quantize(Decimal('0.01'), ROUND_HALF_UP)
        return {
            'employee': contribution,
            'employer': contribution
        }

    def calculate_nhif(self, gross_pay: Decimal) -> Decimal:
        """Calculate NHIF contribution based on salary band"""
        for upper_limit, amount in self.NHIF_BANDS:
            if upper_limit is None or gross_pay <= upper_limit:
                return amount
        return self.NHIF_BANDS[-1][1]

    def calculate_housing_levy(self, gross_pay: Decimal) -> Dict[str, Decimal]:
        """Calculate Housing Levy (1.5% each)"""
        levy = (gross_pay * self.HOUSING_LEVY_RATE).quantize(Decimal('0.01'), ROUND_HALF_UP)
        return {
            'employee': levy,
            'employer': levy
        }

    def calculate_paye(
        self,
        gross_pay: Decimal,
        nssf_employee: Decimal,
        nhif: Decimal,
        housing_levy: Decimal
    ) -> Decimal:
        """
        Calculate PAYE using graduated tax bands
        Taxable income = Gross - NSSF - NHIF - Housing Levy
        """
        taxable_income = gross_pay - nssf_employee - nhif - housing_levy

        if taxable_income <= 0:
            return Decimal('0')

        tax = Decimal('0')
        remaining = taxable_income

        for band_amount, rate in self.PAYE_BANDS:
            if band_amount is None:
                # Top bracket - tax remaining at this rate
                tax += remaining * rate
                break

            if remaining <= band_amount:
                tax += remaining * rate
                break
            else:
                tax += band_amount * rate
                remaining -= band_amount

        # Apply personal relief
        tax = max(Decimal('0'), tax - self.PERSONAL_RELIEF)

        return tax.quantize(Decimal('0.01'), ROUND_HALF_UP)

    def calculate_all(
        self,
        gross_pay: Decimal,
        helb_deduction: Decimal = Decimal('0')
    ) -> Dict:
        """Calculate all statutory deductions for an employee"""
        gross = Decimal(str(gross_pay))

        nssf = self.calculate_nssf(gross)
        nhif = self.calculate_nhif(gross)
        housing_levy = self.calculate_housing_levy(gross)
        paye = self.calculate_paye(gross, nssf['employee'], nhif, housing_levy['employee'])

        total_deductions = (
            nssf['employee'] + nhif + housing_levy['employee'] + paye + helb_deduction
        )

        net_pay = gross - total_deductions

        return {
            'gross_pay': gross,
            'nssf_employee': nssf['employee'],
            'nssf_employer': nssf['employer'],
            'nhif': nhif,
            'housing_levy_employee': housing_levy['employee'],
            'housing_levy_employer': housing_levy['employer'],
            'paye': paye,
            'helb': helb_deduction,
            'total_deductions': total_deductions,
            'net_pay': net_pay,
        }
