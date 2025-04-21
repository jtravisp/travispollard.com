export function calculatePSI() {
    const riderweight = parseInt((document.getElementById('riderweight') as HTMLInputElement)?.value || '0');
    const bikeweight = parseInt((document.getElementById('bikeweight') as HTMLInputElement)?.value || '0');
    const tubeless = (document.getElementById('tubeless') as HTMLSelectElement)?.value === 'true';
    const tirewidth = parseInt((document.getElementById('tirewidth') as HTMLSelectElement)?.value || '25');
  
    const totalweight = riderweight + bikeweight;
    const baseline = 100;
    const psiAdjustments: Record<number, { light: number; medium: number; heavy: number }> = {
      23: { light: -5, medium: 0, heavy: 5 },
      25: { light: -20, medium: -15, heavy: -10 },
      28: { light: -35, medium: -30, heavy: -25 },
      30: { light: -40, medium: -35, heavy: -30 },
      32: { light: -43, medium: -38, heavy: -33 }
    };
  
    let weightRange: keyof typeof psiAdjustments[number];
    if (totalweight < 180) weightRange = 'light';
    else if (totalweight > 200) weightRange = 'heavy';
    else weightRange = 'medium';
  
    let psi = baseline + (psiAdjustments[tirewidth]?.[weightRange] ?? 0);
    if (tubeless) psi -= 10;
  
    const message = `Your recommended tire PSI is ${psi}.`;
    const output = document.getElementById("psi");
    if (output) output.textContent = message;
  }
