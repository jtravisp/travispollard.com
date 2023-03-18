
var riderweight, bikeweight, tubeless, tirewidth;

function psi() {
    riderweight = document.getElementById('riderweight').value;
    bikeweight = document.getElementById('bikeweight').value;
    tubeless = document.getElementById('tubeless').value;
    tirewidth = document.getElementById('tirewidth').value;

    var totalweight = parseInt(riderweight) + parseInt(bikeweight);
    var baseline = 100;
    var psiAdjustments = {
        23: { light: -5, medium: 0, heavy: 5 },
        25: { light: -20, medium: -15, heavy: -10 },
        28: { light: -35, medium: -30, heavy: -25 },
        30: { light: -40, medium: -35, heavy: -30 },
        32: { light: -43, medium: -38, heavy: -33 }
    };

    var weightRange;
    if (totalweight < 180) {
        weightRange = 'light';
    } else if (totalweight > 200) {
        weightRange = 'heavy';
    } else {
        weightRange = 'medium';
    }

    var psi = baseline + (psiAdjustments[tirewidth][weightRange] || 0);

    if (tubeless == "true") {
        psi -= 10;
    }

    var message = "Your recommended tire PSI is " + psi + ".";
    document.getElementById("psi").innerHTML = message;
}





/*
// For 700cc wheeles only
// Rider weight- over 180 + 3 per 20 lbs
    //under 180 - 3 per 20 lbs
// Bike weight (include typical weight)
    // add to rider weight before calculation
// Tubeless checkbox?
    // -10 psi
// Tire width selector
    //23 100 psi, adjust for weight
    //25 - 15% baseline (85)
    //28 - 30% baseline (70)
    //30 - 35% (65)
    //32 - 35%

// pseudo code
accept variables from user:
riderWeight
bikeWeight
tubeless -True/False
tireWidth

run variables through psi formula
return recommended psi
*/