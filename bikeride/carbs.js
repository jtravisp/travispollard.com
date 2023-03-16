/*
// Carbohydrates are the body’s primary energy source when cycling. If you don't plan your carb intake during longer rides, prepare to "bonk" before you get back home!
1 g per kg weight OR 1g per 2.2 lbs
*/

var weight ;

function carbs() {

    weight = document.getElementById('weight').value;
    
    var carbs = (weight / 3).toFixed(1)
        
    var carbsbananas = (carbs / 27).toFixed(1)

    var carbsgu = (carbs / 23).toFixed(1)

    var carbstaco = (carbs / 14).toFixed(1)

    var message = "Your recommended number of carbs per hour is " + carbs + ". You could get this amount of nutrition from " + carbsbananas + " bananas, " + carbsgu + " Gu gel packets, or " + carbstaco + " tacos per hour. (Don't forget to take into account any carbs you're getting from your sports drink or other supplements.)";
        
    document.getElementById("carbs").innerHTML = message;
}
