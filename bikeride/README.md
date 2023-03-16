# CS50 Final Project
## Austin Bike Ride Planner

#### Video Demo: https://youtu.be/UJE7-VTVdXE

#### Description:
This is a web page to help you plan your next bike ride in Austin! Check the weather, suggested bike tire pressure, nutrition recommendations, and more. In designing this site I learned more about leveraging Bootstrap to easily make a site look modern and clean. One challenege I overcame was learning how to use JavaScript to update pieces of my HTML code. At first my HTML was "submitting" the page. The JS was working, but the entire page would reload, eliminating the updated HTML. This is how I learned about using "onclick" instead of "submit" with my forms. Using "onclick" to call a JS function allowed only that piece of HTML to be updated, revealing the result of the user's request.

CS50 has been an amazing course. Thank you to the instructors and everyone who played a part in providing this resource to the public.

#### Features:
- Utilizes HTML, CSS, JavaScript, Bootstrap
- Bike tire PSI calculator (JS: psi.js). The user inputs relevant data and gets the suggested PSI to inflate their bike tires. This is a process that every cyclist goes through before a ride. There are a lot of factors involved, so it's easy to forget the ideal PSI for your bike. This is a practical tool that I will use before every ride.
- Nutrition calcultor (JS: carbs.js). The user input their weight and gets the suggest nutrition per hour for a ride, including how much of different types of food popular with cyclists..
- Personal Strava widget. Shows my recent rides. 
- Cycling checklist. Helps the user to not forget anything important you will need on your ride. Bootstrap helps with the formatting. Checkboxes can be checked by the user, indicating they have that item ready.
- Random Kanye quote generator. Created using a tutorial to help me learn how to use an API and get my JS to talk to my HTML (https://www.itzami.com/blog/build-a-quote-generator-with-javascript-your-first-api-project). Decided to keep it on the page for fun.
- CSS framework is Bootstrap
- Weather widget courtesy of weatherwidget.io
- Bootstrap 12 column format. Page is designed to render in two large columns on larger displays (such as laptops and desktops) and a songle column on mobile devies.

#### TO-DO
- Streamline psi.js code. There should be a less verbose way of calculating the suggested PSI.
-Implement an "Events" feature to create group ride information, including a ride sign-up, route sharing, and comments.
- Implement a login. Would allow users to contribute to ride info, subit their own rides, and show their own personal Strava history.
