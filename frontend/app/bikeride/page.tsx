'use client';

import Link from 'next/link';
import { useEffect } from 'react';
import { calculateCarbs } from './utils/carbs';
import { calculatePSI } from './utils/psi';

export default function BikeRidePlanner() {
    useEffect(() => {
        document.documentElement.setAttribute('data-theme', 'nord');
        const script = document.createElement('script');
        script.src = 'https://weatherwidget.io/js/widget.min.js';
        script.async = true;
        document.body.appendChild(script);
        return () => {
            document.documentElement.setAttribute('data-theme', 'business');
        };
    }, []);

  return (
    <main className="min-h-screen bg-base-100 text-base-content px-4 py-8">
      <div className="max-w-5xl mx-auto">

        {/* Custom Header */}
        <header className="flex flex-col sm:flex-row justify-between items-center mb-10">
          <h1 className="text-3xl md:text-4xl font-extrabold font-sans text-base-content">Austin Bike Ride Planner</h1>
          <nav>
            <ul className="flex flex-wrap gap-4 text-sm font-medium text-base-content">
              <li><Link href="/" className="link link-hover">Home</Link></li>
              <li><Link href="/resume" className="link link-hover">Resume</Link></li>
              <li><a href="https://www.linkedin.com/in/travis-pollard" target="_blank" className="link link-hover">LinkedIn</a></li>
              <li><a href="https://medium.com/@travis_17385" target="_blank" className="link link-hover">Medium</a></li>
              <li><a href="/bikeride" className="link link-hover">Bike Ride Planner</a></li>
            </ul>
          </nav>
        </header>

        {/* Hero Section */}
        <section className="text-center mb-6 md:mb-10">
          <img src="/images/bike.png" alt="Bike Icon" className="mx-auto w-32 md:w-48" />
          <h2 className="text-lg md:text-xl font-bold">Make sure you are ready for that weekend ride!</h2>
          <p className="text-base md:text-lg mt-2">Check the weather, calculate tire pressure, plan nutrition, and pack your gear.</p>
        </section>

        <a className="weatherwidget-io block text-center mb-10" href="https://forecast7.com/en/30d27n97d74/austin/" data-label_1="Austin" data-label_2="Weather" data-theme="original">Austin Weather</a>

        {/* Tools Section in Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
          <div className="card bg-base-200 shadow-md p-4 w-full">
            <h3 className="text-lg md:text-2xl font-semibold mb-4">Bike Tire PSI Calculator</h3>
            <form id="psi-form" className="space-y-4">
              <input type="number" id="riderweight" placeholder="Rider lbs" className="input input-bordered w-full" />
              <input type="number" id="bikeweight" placeholder="Bike lbs" className="input input-bordered w-full" />
              <div>
                <select id="tirewidth" className="select select-bordered w-full mt-1" aria-label="Tire Width (700c)">
                  <option disabled selected>Choose Tire Width</option>
                  {[23, 25, 28, 30, 32].map(width => (
                    <option key={width} value={width}>{width}</option>
                  ))}
                </select>
              </div>
              <select id="tubeless" className="select select-bordered w-full">
                <option value="true">Tubeless</option>
                <option value="false">Not Tubeless</option>
              </select>
              <button type="button" className="btn btn-primary w-full" onClick={calculatePSI}>Get Suggested PSI</button>
            </form>
            <div id="psi" className="mt-4 text-xl italic"></div>
          </div>

          <div className="card bg-base-200 shadow-md p-4 w-full">
            <h3 className="text-lg md:text-2xl font-semibold mb-4">Bike Ride Nutrition Calculator</h3>
            <form id="carbs-form" className="space-y-4">
              <input type="number" id="weight" placeholder="Cyclist lbs" className="input input-bordered w-full" />
              <button type="button" className="btn btn-primary w-full" onClick={calculateCarbs}>Get Suggested Carbs</button>
            </form>
            <div id="carbs" className="mt-4 text-xl italic"></div>
          </div>
        </div>

        {/* Ride Summary & Checklist */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
          <div className="text-center">
            <h3 className="text-2xl font-semibold mb-4">My Latest Rides</h3>
            <div className="w-full max-w-md mx-auto aspect-[4/3]">
              <iframe
                className="w-full h-full"
                frameBorder="0"
                scrolling="no"
                src="https://www.strava.com/athletes/542739/latest-rides/c56d3cc83420c1133797aec08669049d951dedec"
              ></iframe>
            </div>
          </div>

          <div>
            <h3 className="text-2xl font-semibold mb-2">Cycling Checklist</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
              <div>
                <h4 className="font-bold mt-4">Gear</h4>
                {["Road Bike", "Helmet", "Two Water Bottles", "Under Seat Bag", "Lights", "Pump"].map(item => (
                  <div className="form-control" key={item}>
                    <label className="label cursor-pointer">
                      <input type="checkbox" className="checkbox mr-2" />
                      <span className="label-text">{item}</span>
                    </label>
                  </div>
                ))}
              </div>
              <div>
                <h4 className="font-bold mt-4">Clothing</h4>
                {["Bib", "Jersey", "Socks", "Gloves", "Shoes"].map(item => (
                  <div className="form-control" key={item}>
                    <label className="label cursor-pointer">
                      <input type="checkbox" className="checkbox mr-2" />
                      <span className="label-text">{item}</span>
                    </label>
                  </div>
                ))}

                <h4 className="font-bold mt-4">Other Stuff</h4>
                {["Sunglasses", "Bike Computer", "Heart Rate Monitor", "Food/Nutrition", "Cell Phone", "Road ID", "Driver License/Credit Card"].map(item => (
                  <div className="form-control" key={item}>
                    <label className="label cursor-pointer">
                      <input type="checkbox" className="checkbox mr-2" />
                      <span className="label-text">{item}</span>
                    </label>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Easter Egg */}
        <div className="mockup-code w-full max-w-2xl mx-auto text-left my-12 text-base md:text-lg font-mono">
          <pre data-prefix="$" className="text-info">
            <code># 🚴 Ride bikes!</code>
          </pre>
        </div>

        {/* Footer Images */}
        <div className="text-center mt-10">
          <img src="/images/skyline.png" alt="Austin Skyline" className="mx-auto mb-4 w-full max-w-2xl" />
          <img src="/images/horns.png" alt="Horns Logo" className="mx-auto w-60" />
        </div>
      </div>
    </main>
  );
}
