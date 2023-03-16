var riderweight, bikeweight, tubeless, tirewidth ;

function psi() {

    riderweight = document.getElementById('riderweight').value;
    bikeweight = document.getElementById('bikeweight').value;
    tubeless = document.getElementById('tubeless').value;
    tirewidth = document.getElementById('tirewidth').value;

    var totalweight = parseInt(riderweight) + parseInt(bikeweight);
    var baseline = 100;
    var psi = 0;

    // Shorten this code...
    if (tirewidth == 23) {
        if (totalweight < 180) {
            psi = baseline - 5;
        } else if (totalweight > 200) {
            psi = baseline + 5;
        } else {
            psi = baseline;
        }
        if (tubeless == "true") {
            psi -= 10;
        }
    } else if (tirewidth == 25) {
        if (totalweight < 180) {
            psi = baseline - 20;
        } else if (totalweight > 200) {
            psi = baseline - 10;
        } else {
            psi = baseline - 15;
        }
        if (tubeless == "true") {
            psi -= 10;
        }
    } else if (tirewidth == 28) {
        if (totalweight < 180) {
            psi = baseline - 35;
        } else if (totalweight > 200) {
            psi = baseline - 25;
        } else {
            psi = baseline - 30;
        }
        if (tubeless == "true") {
            psi -= 10;
        }
    } else if (tirewidth == 30) {
        if (totalweight < 180) {
            psi = baseline - 40;
        } else if (totalweight > 200) {
            psi = baseline - 30;
        } else {
            psi = baseline - 35;
        }
        if (tubeless == "true") {
            psi -= 10;
        }
    } else if (tirewidth == 32) {
        if (totalweight < 180) {
            psi = baseline - 43;
        } else if (totalweight > 200) {
            psi = baseline - 33;
        } else {
            psi = baseline - 38;
        }
        if (tubeless == "true") {
            psi -= 10;
        }
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