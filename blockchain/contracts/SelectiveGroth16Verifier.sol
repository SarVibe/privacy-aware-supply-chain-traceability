// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract SelectiveGroth16Verifier {
    // Scalar field size
    uint256 constant r    = 21888242871839275222246405745257275088548364400416034343698204186575808495617;
    // Base field size
    uint256 constant q   = 21888242871839275222246405745257275088696311157297823662689037894645226208583;

    // Verification Key data
    uint256 constant alphax  = 20584380707810976424754859510126474320243036232700952918051822372702415289715;
    uint256 constant alphay  = 13828512875791138586592715685202566010620606230539663422460989868372935296158;
    uint256 constant betax1  = 15774664603188486080953364456609421638743591237699450702291669469956620918374;
    uint256 constant betax2  = 20536084813056641934707587764342000823936549106635568128303902667247463344387;
    uint256 constant betay1  = 323201843340685569075978815311727219882313798996430760274378064078074436797;
    uint256 constant betay2  = 147002804681952386444047854521250172141986404189325432255991688168492853402;
    uint256 constant gammax1 = 11559732032986387107991004021392285783925812861821192530917403151452391805634;
    uint256 constant gammax2 = 10857046999023057135944570762232829481370756359578518086990519993285655852781;
    uint256 constant gammay1 = 4082367875863433681332203403145435568316851327593401208105741076214120093531;
    uint256 constant gammay2 = 8495653923123431417604973247489272438418190587263600148770280649306958101930;
    uint256 constant deltax1 = 648160933548973761347032099933968136038341058939017691064375558473586782849;
    uint256 constant deltax2 = 5803653778314894801238367137691165474721326683848103687563381675905568446910;
    uint256 constant deltay1 = 6713535123216973233466840413230604458224376860785984766885983234744573464694;
    uint256 constant deltay2 = 19217599883448215725150031176661732167155139450967766343850177772132792034224;

    
    uint256 constant IC0x = 221344506657651449835470604276422652893553969305912936905610422401388208484;
    uint256 constant IC0y = 5368089933634015727299603847257201653394656488014119937604384817327380587584;
    
    uint256 constant IC1x = 7397134260264069080502367216504941651870373424255661117666964133017172238272;
    uint256 constant IC1y = 18882753636556113569576882160095940094396936213709148048653343590442909877444;
    
    uint256 constant IC2x = 21024590463325880664953611243622067387002471045915112016371396758163294522624;
    uint256 constant IC2y = 16472267108828799749952192485366968072567170212465894443663844398114383600515;
    
    uint256 constant IC3x = 11312635305863840480378373592501021247784541841176634960936208438670537700427;
    uint256 constant IC3y = 21435967972163173005939009200209063761330319293111890799576737028900495397731;
    
    uint256 constant IC4x = 9502804466984524901318460881718725666412758955870549591101445104981051271817;
    uint256 constant IC4y = 17033039975338064983646902750009444456538215919698760635281255005110397447062;
    
    uint256 constant IC5x = 2680871673164669560723070149809204431106533725043659290943527968525721403255;
    uint256 constant IC5y = 20408362661764750496794967913752921578620472777881577426226312124401331294442;
    
    uint256 constant IC6x = 11329150436445978305405849682288129147580238230072879616012472536353478943717;
    uint256 constant IC6y = 7669233002733717801498725100463473432834170763382242753819022259633086489358;
    
    uint256 constant IC7x = 5449878698990833778182850745112286657000253768432151370278978355417643958329;
    uint256 constant IC7y = 860974150497142850049568823025722270896843727796035513216601503312459814639;
    
    uint256 constant IC8x = 15594885309002131235159532179731156696286810160864700149779191810988098515044;
    uint256 constant IC8y = 17804676312011502790696963077416297745566014720223015840412203205418435666138;
    
    uint256 constant IC9x = 17017713736421285845459535151249654020178980667500727630637446414574849137463;
    uint256 constant IC9y = 11495732879771732662517483922635583268624401901635503972548178035986548020070;
    
    uint256 constant IC10x = 17168287104871832409839870105664650893815956955521483359357327252438010147055;
    uint256 constant IC10y = 2921209981838065789869736037580556348677180705474995049046609216268516036423;
    
    uint256 constant IC11x = 9422068635168566279528054760158933264420869823938284914239613760148147431045;
    uint256 constant IC11y = 19119809016297115452425563900078389430080594971153504204340371416213390587669;
    
 
    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(uint[2] calldata _pA, uint[2][2] calldata _pB, uint[2] calldata _pC, uint[11] calldata _pubSignals) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }
            
            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x
                
                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))
                
                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))
                
                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))
                
                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))
                
                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))
                
                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))
                
                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))
                
                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))
                
                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))
                
                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))
                
                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))
                

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))


                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)


                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations âˆˆ F
            
            checkField(calldataload(add(_pubSignals, 0)))
            
            checkField(calldataload(add(_pubSignals, 32)))
            
            checkField(calldataload(add(_pubSignals, 64)))
            
            checkField(calldataload(add(_pubSignals, 96)))
            
            checkField(calldataload(add(_pubSignals, 128)))
            
            checkField(calldataload(add(_pubSignals, 160)))
            
            checkField(calldataload(add(_pubSignals, 192)))
            
            checkField(calldataload(add(_pubSignals, 224)))
            
            checkField(calldataload(add(_pubSignals, 256)))
            
            checkField(calldataload(add(_pubSignals, 288)))
            
            checkField(calldataload(add(_pubSignals, 320)))
            

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
             return(0, 0x20)
         }
     }
 }
