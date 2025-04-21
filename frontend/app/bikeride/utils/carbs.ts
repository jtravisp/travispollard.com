export function calculateCarbs() {
    const weight = parseFloat((document.getElementById("weight") as HTMLInputElement)?.value || '0');
    const carbs = (weight / 3).toFixed(1);
    const carbsbananas = (parseFloat(carbs) / 27).toFixed(1);
    const carbsgu = (parseFloat(carbs) / 23).toFixed(1);
    const carbstaco = (parseFloat(carbs) / 14).toFixed(1);
  
    const message = `Your recommended number of carbs per hour is ${carbs}. You could get this amount of nutrition from ${carbsbananas} bananas, ${carbsgu} Gu gel packets, or ${carbstaco} tacos per hour. (Don't forget to take into account any carbs you're getting from your sports drink or other supplements.)`;
  
    const output = document.getElementById("carbs");
    if (output) output.textContent = message;
  }
  